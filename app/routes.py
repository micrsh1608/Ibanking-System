from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models import Account, User
from app.schemas import (
    AccountResponse,
    LoginRequest,
    TokenResponse,
    UserResponse,
)
from app.security import (
    DUMMY_HASH,
    create_access_token,
    verify_password,
)


router = APIRouter()


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
        select(User).where(User.username == data.username)
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