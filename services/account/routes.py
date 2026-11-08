from fastapi import APIRouter, Depends, HTTPException, Response
import os
import json
import hmac

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from services.account.database import SessionLocal, engine
from shared.locking import session_lock
from shared.mailer import Mailer, get_mailer, resolve_email_channel
from shared.time import utcnow
from services.account import email_verification as email_proof
from services.account.dependencies import get_current_user, get_db
from services.account.models import Account, User
from services.account.schemas import (
    AccountResponse,
    LoginRequest,
    TokenResponse,
    UserResponse,
    ProfileUpdate,
    EmailVerificationRequest,
    EmailResendRequest,
)
from services.account.security import (
    DUMMY_HASH,
    create_access_token,
    verify_password,
)


router = APIRouter()


@router.get('/app-config', tags=['Application'])
def public_config():
    return {'email_delivery': resolve_email_channel('smtp'), 'account_email_routing': True}


def profile_guard(acquired):
    if not acquired:
        raise HTTPException(409, 'Hồ sơ đang được xử lý. Vui lòng thử lại.')


def active_profile(db, user_id):
    user=db.get(User,user_id)
    if user is None or not user.is_active:
        raise HTTPException(403,'Người dùng đã bị vô hiệu hóa')
    return user


@router.put('/users/me', response_model=UserResponse, tags=['Users'], responses={202:{'model':UserResponse,'description':'Email mới chờ xác minh; hồ sơ hiện tại chưa đổi'}})
def update_profile(data: ProfileUpdate, response: Response, current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db), mailer: Mailer = Depends(get_mailer)):
    user_id=current_user.id
    db.rollback()
    with session_lock(engine,'profile-email:'+str(user_id)) as acquired:
        profile_guard(acquired)
        with SessionLocal.begin() as session:
            user=active_profile(session,user_id)
            if not verify_password(data.current_password,user.password_hash):
                raise HTTPException(403,'Mật khẩu xác nhận không đúng; thông tin chưa được thay đổi.')
            profile=data.model_dump(exclude={'current_password'})
            # Every profile update requires proof at the submitted address.
            # Commit the complete pending profile only after the user enters it.
            message=email_proof.stage(user,profile)
            response.status_code=202
            session.flush()
            result=UserResponse.model_validate(user)
        if message:email_proof.deliver_or_revoke(user_id,message,mailer)
        return result


@router.post('/users/me/email-verification/confirm',response_model=UserResponse,tags=['Users'])
def confirm_email(data: EmailVerificationRequest,current_user: User=Depends(get_current_user),db: Session=Depends(get_db)):
    user_id=current_user.id
    db.rollback()
    with session_lock(engine,'profile-email:'+str(user_id)) as acquired:
        profile_guard(acquired)
        error=None
        with SessionLocal.begin() as session:
            user=active_profile(session,user_id)
            if not user.email_code_hash or user.email_challenge_id!=str(data.challenge_id):
                raise HTTPException(409,'Yêu cầu xác minh đã hết hiệu lực hoặc đã được sử dụng.')
            if user.email_pending_channel and user.email_pending_channel != user.email_delivery:
                email_proof.clear_pending(user)
                error=HTTPException(409,'Kênh nhận email đã thay đổi. Vui lòng yêu cầu mã xác minh mới.')
            elif user.email_code_expires_at is None or user.email_code_expires_at<=utcnow():
                raise HTTPException(400,'Mã xác minh email đã hết hạn. Vui lòng yêu cầu mã mới.')
            elif user.email_code_attempts>=5:
                raise HTTPException(429,'Đã nhập sai mã xác minh email quá 5 lần. Vui lòng yêu cầu mã mới.')
            elif not hmac.compare_digest(user.email_code_hash,email_proof.hash_code(user,data.code)):
                user.email_code_attempts+=1
                error=HTTPException(400,'Mã xác minh email không đúng.')
            else:
                profile=ProfileUpdate(**json.loads(user.email_pending_profile),current_password='verified-proof').model_dump(exclude={'current_password'})
                for name,value in profile.items():setattr(user,name,value)
                user.email_verified_at=utcnow()
                email_proof.clear_pending(user)
            session.flush()
            result=UserResponse.model_validate(user)
        if error:raise error
        return result


@router.post('/users/me/email-verification/resend',response_model=UserResponse,status_code=202,tags=['Users'])
def resend_email(data: EmailResendRequest,current_user: User=Depends(get_current_user),db: Session=Depends(get_db),mailer: Mailer=Depends(get_mailer)):
    user_id=current_user.id
    db.rollback()
    with session_lock(engine,'profile-email:'+str(user_id)) as acquired:
        profile_guard(acquired)
        with SessionLocal.begin() as session:
            user=active_profile(session,user_id)
            if not verify_password(data.current_password,user.password_hash):
                raise HTTPException(403,'Mật khẩu xác nhận không đúng; thông tin chưa được thay đổi.')
            if not user.email_pending_profile:raise HTTPException(409,'Không có email đang chờ xác minh.')
            message=email_proof.stage(user,json.loads(user.email_pending_profile))
            session.flush()
            result=UserResponse.model_validate(user)
        email_proof.deliver_or_revoke(user_id,message,mailer)
        return result


@router.delete('/users/me/email-verification',response_model=UserResponse,tags=['Users'])
def cancel_email(current_user: User=Depends(get_current_user),db: Session=Depends(get_db)):
    user_id=current_user.id
    db.rollback()
    with session_lock(engine,'profile-email:'+str(user_id)) as acquired:
        profile_guard(acquired)
        with SessionLocal.begin() as session:
            user=active_profile(session,user_id)
            email_proof.clear_pending(user)
            session.flush()
            return UserResponse.model_validate(user)


@router.post(
    "/auth/login",
    response_model=TokenResponse,
    tags=["Authentication"],
)
def login(
    data: LoginRequest,
    db: Session = Depends(get_db),
):
    user = db.scalar(
        select(User).where(func.lower(User.username) == data.username)
    )

    stored_hash = (
        user.password_hash if user is not None else DUMMY_HASH
    )
    password_valid = verify_password(data.password, stored_hash)

    if user is None or not password_valid:
        raise HTTPException(
            status_code=401,
            detail="Sai tên đăng nhập hoặc mật khẩu",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="Người dùng đã bị vô hiệu hóa",
        )

    return TokenResponse(
        access_token=create_access_token(user.id)
    )


@router.get(
    "/users/me",
    response_model=UserResponse,
    tags=["Users"],
)
def read_current_user(
    current_user: User = Depends(get_current_user),
):
    return current_user


@router.get(
    "/accounts/me",
    response_model=AccountResponse,
    tags=["Accounts"],
)
def read_current_account(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    account = db.scalar(
        select(Account).where(
            Account.user_id == current_user.id
        )
    )

    if account is None:
        raise HTTPException(
            status_code=404,
            detail="Người dùng chưa có tài khoản ngân hàng",
        )

    return account
