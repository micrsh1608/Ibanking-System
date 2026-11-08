import hashlib
import hmac
import json
import os
from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy import and_, or_, select

from services.payment.clients import Services, UpstreamError, get_services
from services.payment.coordinator import TERMINAL, load_payment, payment_view, process_payment
from services.payment.database import SessionLocal, engine
from services.payment.models.payment import PaymentItem, PaymentTransaction
from services.payment.otp import allocate_code, generate_otp, hash_otp
from services.payment.schemas import OTPChallengeView, OTPVerifiedView, OTPVerifyRequest, PaymentCreate, PaymentPage, PaymentView
from shared.auth import Principal, require_principal
from shared.locking import session_lock
from shared.time import utcnow
from shared.mailer import resolve_email_channel
from services.payment.mailer import Mailer, MailError, get_mailer
from services.payment.email_templates import otp_message
from services.payment.policy import TERMS_VERSION, is_legacy_draft, validate_payer

router = APIRouter(prefix='/api/v1/payments', tags=['Payments'])
CANCELLED_DRAFT = 'Người dùng đã hủy giao dịch trước khi xử lý.'


def snapshot_email_channel(user):
    # Account is the authority. Legacy clients/stubs may not yet expose delivery.
    if 'email_delivery' not in user:
        return 'smtp'
    channel = user['email_delivery']
    if channel != 'smtp':
        raise HTTPException(503, 'Kênh nhận email của tài khoản chưa được cấu hình. Vui lòng liên hệ quản trị viên.')
    return channel


def owned(db, key, user_id):
    row = db.get(PaymentTransaction, key)
    if row is None or row.payer_user_id != user_id:
        raise HTTPException(404, 'Không tìm thấy giao dịch')
    return row


def require_lock(acquired):
    if not acquired:
        raise HTTPException(409, 'Giao dịch đang xử lý; thử lại cùng payment_id')


@router.post('', response_model=PaymentView, status_code=201)
def create_payment(data: PaymentCreate, response: Response,
    idempotency_key: UUID = Header(alias='Idempotency-Key'),
    principal: Principal = Depends(require_principal), services: Services = Depends(get_services)):
    key = str(idempotency_key)
    # Preserve the established ALL_UNPAID fingerprint for retries across upgrade.
    fingerprint = hashlib.sha256(json.dumps({'user_id': principal.user_id, 'mssv': data.mssv,
        'selection_mode': data.selection_mode, 'invoice_ids': []}, sort_keys=True).encode()).hexdigest()
    with session_lock(engine, 'payment:' + key) as acquired:
        require_lock(acquired)
        with SessionLocal() as db:
            previous = db.get(PaymentTransaction, key)
            if previous is not None:
                if previous.payer_user_id != principal.user_id:
                    raise HTTPException(404, 'Không tìm thấy giao dịch')
                if previous.request_hash != fingerprint:
                    raise HTTPException(409, 'Idempotency-Key đã dùng với dữ liệu khác')
                response.status_code = 200
                return PaymentView.model_validate(previous)
        # All remote reads occur after closing the previous read transaction.
        user, account = services.payer(principal.token)
        if user.get('id') != principal.user_id:
            raise UpstreamError(503, 'Danh tính Account không khớp JWT')
        validate_payer(user)
        email_channel = snapshot_email_channel(user)
        if account.get('status') != 'ACTIVE':
            raise HTTPException(409, 'Tài khoản không hoạt động')
        snapshot = services.invoices(data.mssv)
        if any(item['status'] == 'RESERVED' for item in snapshot['invoices']):
            raise HTTPException(409, 'Công nợ đang được giao dịch khác xử lý; chờ kết quả rồi tra cứu lại')
        available = {item['id']: item for item in snapshot['invoices'] if item['status'] == 'UNPAID'}
        ids = sorted(available)
        if not ids or len(ids) > 100 or any(invoice_id not in available for invoice_id in ids):
            raise HTTPException(409, 'Hóa đơn không tồn tại, đang xử lý hoặc đã thanh toán')
        total = sum((Decimal(available[invoice_id]['amount_due']) for invoice_id in ids), Decimal('0.00'))
        if not Decimal('0.00') < total <= Decimal('9999999999999999.99'):
            raise HTTPException(409, 'Tổng tiền vượt giới hạn giao dịch')
        if Decimal(account['balance']) < total:
            raise HTTPException(409, 'Số dư khả dụng không đủ để thanh toán toàn bộ công nợ')
        with SessionLocal.begin() as db:
            payment = PaymentTransaction(payment_id=key, transaction_code='TXN-' + UUID(key).hex.upper(),
                request_hash=fingerprint, payer_user_id=principal.user_id, account_id=account['id'],
                payer_name=user['full_name'], payer_email=user['email'], mssv=data.mssv,
                email_channel=email_channel,
                student_name=snapshot['full_name'], selection_mode=data.selection_mode, total_amount=total,
                terms_version=TERMS_VERSION, terms_accepted_at=utcnow(),
                items=[PaymentItem(invoice_id=invoice_id, invoice_version=available[invoice_id]['version'],
                    semester=available[invoice_id]['semester'], amount=Decimal(available[invoice_id]['amount_due'])) for invoice_id in ids])
            db.add(payment)
            db.flush()
        return payment_view(key, principal.user_id)


@router.get('', response_model=PaymentPage)
def history(limit: int = Query(20, ge=1, le=100), cursor: UUID | None = None,
    principal: Principal = Depends(require_principal)):
    with SessionLocal() as db:
        statement = select(PaymentTransaction).where(PaymentTransaction.payer_user_id == principal.user_id)
        if cursor is not None:
            before = owned(db, str(cursor), principal.user_id)
            statement = statement.where(or_(PaymentTransaction.created_at < before.created_at,
                and_(PaymentTransaction.created_at == before.created_at, PaymentTransaction.payment_id < before.payment_id)))
        rows = db.scalars(statement.order_by(PaymentTransaction.created_at.desc(), PaymentTransaction.payment_id.desc()).limit(limit + 1)).all()
        return {'items': [PaymentView.model_validate(row) for row in rows[:limit]],
            'next_cursor': rows[limit - 1].payment_id if len(rows) > limit else None}


@router.get('/{payment_id}', response_model=PaymentView)
def get_payment(payment_id: UUID, principal: Principal = Depends(require_principal)):
    return payment_view(str(payment_id), principal.user_id)


def require_verified_recipient(principal, payment, services):
    try:
        user, account = services.payer(principal.token)
    except UpstreamError as error:
        raise HTTPException(error.status, error.detail) from None
    validate_payer(user)
    if user.get('id') != principal.user_id or account.get('id') != payment.account_id:
        raise HTTPException(409, 'Tài khoản không khớp giao dịch')
    if user['email'] != payment.payer_email:
        raise HTTPException(409, 'Email của giao dịch cũ đã thay đổi. Vui lòng tạo giao dịch mới với email đã xác minh.')
    if resolve_email_channel(snapshot_email_channel(user)) != payment.email_delivery:
        raise HTTPException(409, 'Kênh nhận email đã thay đổi. Vui lòng tạo giao dịch mới sau khi xác minh email.')


@router.post('/{payment_id}/send-otp', response_model=OTPChallengeView, status_code=202)
def send_otp(payment_id: UUID, principal: Principal = Depends(require_principal), mailer: Mailer = Depends(get_mailer), services: Services = Depends(get_services)):
    key = str(payment_id)
    load_payment(key, principal.user_id)
    with session_lock(engine, 'payment:' + key) as acquired:
        require_lock(acquired)
        require_verified_recipient(principal, load_payment(key, principal.user_id), services)
        with SessionLocal.begin() as db:
            payment = owned(db, key, principal.user_id)
            if is_legacy_draft(payment):
                raise HTTPException(409, 'Giao dịch cũ chưa theo quy tắc thanh toán toàn bộ và điều khoản mới. Vui lòng tạo giao dịch mới.')
            if payment.status not in {'PENDING_OTP', 'OTP_VERIFIED'}:
                raise HTTPException(409, 'Giao dịch không thể cấp OTP')
            now = utcnow()
            if payment.otp_last_sent_at is not None and (now - payment.otp_last_sent_at).total_seconds() < 60:
                raise HTTPException(429, 'Chờ 60 giây trước khi gửi lại OTP')
            code = allocate_code(db, payment, now, generate_otp)
            payment.challenge_id = str(uuid4())
            payment.otp_expires_at = now + timedelta(minutes=5)
            payment.otp_last_sent_at = now
            payment.otp_verified_at = None
            payment.otp_attempts = 0
            payment.status = 'PENDING_OTP'
            payment.otp_hash = hash_otp(payment, code)
            local, _, domain = payment.payer_email.partition('@')
            result = OTPChallengeView(challenge_id=payment.challenge_id, expires_at=payment.otp_expires_at,
                email_delivery=payment.email_delivery,
                delivery_address=(local[:1] + '***@' + domain) if domain else 'email đã đăng ký')
            subject, body = otp_message(payment, code)
            recipient, challenge_id, channel = payment.payer_email, payment.challenge_id, payment.email_channel
        try:
            mailer.send(recipient=recipient, subject=subject, body=body, message_id=challenge_id, channel=channel)
        except MailError:
            with SessionLocal.begin() as db:
                failed = owned(db, key, principal.user_id)
                failed.otp_hash = failed.challenge_id = failed.otp_expires_at = failed.otp_last_sent_at = None
                failed.otp_fingerprint = None
            raise HTTPException(503, 'Chưa gửi được OTP qua email. Vui lòng thử gửi lại.') from None
        return result


@router.post('/{payment_id}/verify-otp', response_model=OTPVerifiedView)
def verify_otp(payment_id: UUID, data: OTPVerifyRequest, principal: Principal = Depends(require_principal), services: Services = Depends(get_services)):
    key = str(payment_id)
    with session_lock(engine, 'payment:' + key) as acquired:
        require_lock(acquired)
        require_verified_recipient(principal, load_payment(key, principal.user_id), services)
        error = None
        with SessionLocal.begin() as db:
            payment = owned(db, key, principal.user_id)
            if payment.status != 'PENDING_OTP' or payment.otp_verified_at is not None:
                raise HTTPException(409, 'OTP đã được sử dụng hoặc giao dịch đang xử lý')
            if payment.challenge_id != str(data.challenge_id) or payment.otp_hash is None:
                raise HTTPException(400, 'OTP không thuộc giao dịch này')
            if payment.otp_expires_at is None or payment.otp_expires_at <= utcnow():
                raise HTTPException(400, 'OTP đã hết hạn')
            if payment.otp_attempts >= 5:
                raise HTTPException(429, 'Đã nhập sai OTP quá số lần cho phép')
            if not hmac.compare_digest(payment.otp_hash, hash_otp(payment, data.otp)):
                payment.otp_attempts += 1
                error = HTTPException(400, 'OTP không hợp lệ')
            else:
                payment.otp_verified_at = utcnow()
                payment.otp_hash = None
                payment.status = 'OTP_VERIFIED'
        if error is not None:
            raise error
        return {'payment_id': key, 'status': 'OTP_VERIFIED'}


@router.post('/{payment_id}/process', response_model=PaymentView, responses={
    202: {'model': PaymentView, 'description': 'Đang xử lý hoặc đối soát; tra cứu cùng UUID'},
    409: {'description': 'Chưa xác minh OTP, hoặc giao dịch đã thất bại/được hoàn tiền'},
})
def process(payment_id: UUID, response: Response, principal: Principal = Depends(require_principal),
    services: Services = Depends(get_services)):
    key = str(payment_id)
    payment = load_payment(key, principal.user_id)
    if payment.status in {'PENDING_OTP', 'OTP_VERIFIED'}:
        require_verified_recipient(principal, payment, services)
    result = process_payment(key, services)
    response.status_code = 200 if result.status == 'SUCCEEDED' else (409 if result.status in TERMINAL else 202)
    return result


@router.post('/{payment_id}/cancel', response_model=PaymentView, responses={
    409: {'description': 'Chỉ được hủy giao dịch chưa bắt đầu xử lý'},
})
def cancel_draft(payment_id: UUID, principal: Principal = Depends(require_principal)):
    key = str(payment_id)
    load_payment(key, principal.user_id)
    with session_lock(engine, 'payment:' + key) as acquired:
        require_lock(acquired)
        with SessionLocal.begin() as db:
            payment = owned(db, key, principal.user_id)
            if payment.status == 'FAILED' and payment.error_message == CANCELLED_DRAFT:
                return PaymentView.model_validate(payment)
            if payment.status not in {'PENDING_OTP', 'OTP_VERIFIED'}:
                raise HTTPException(409, 'Giao dịch đã bắt đầu xử lý hoặc đã kết thúc; hãy kiểm tra kết quả theo mã hiện tại.')
            payment.status, payment.phase = 'FAILED', 'DONE'
            payment.error_message, payment.next_retry_at = CANCELLED_DRAFT, None
            payment.completed_at = utcnow()
            payment.otp_hash = payment.challenge_id = payment.otp_verified_at = None
            # Keep fingerprint AND original expiry until its allocation deadline.
            # Cancellation revokes use, but must not immediately reissue its code.
            db.flush()
            return PaymentView.model_validate(payment)
