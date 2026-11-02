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
from services.payment.otp import generate_otp, hash_otp
from services.payment.schemas import OTPChallengeView, OTPVerifiedView, OTPVerifyRequest, PaymentCreate, PaymentPage, PaymentView
from shared.auth import Principal, require_principal
from shared.locking import session_lock
from shared.time import utcnow
from services.payment.mailer import Mailer, MailError, get_mailer
from services.payment.email_templates import otp_message

router = APIRouter(prefix='/api/v1/payments', tags=['Payments'])


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
    fingerprint = hashlib.sha256(json.dumps({'user_id': principal.user_id, **data.model_dump()}, sort_keys=True).encode()).hexdigest()
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
        if account.get('status') != 'ACTIVE':
            raise HTTPException(409, 'Tài khoản không hoạt động')
        snapshot = services.invoices(data.mssv)
        available = {item['id']: item for item in snapshot['invoices'] if item['status'] == 'UNPAID'}
        ids = sorted(available) if data.selection_mode == 'ALL_UNPAID' else data.invoice_ids
        if not ids or len(ids) > 100 or any(invoice_id not in available for invoice_id in ids):
            raise HTTPException(409, 'Hóa đơn không tồn tại, đang xử lý hoặc đã thanh toán')
        total = sum((Decimal(available[invoice_id]['amount_due']) for invoice_id in ids), Decimal('0.00'))
        if not Decimal('0.00') < total <= Decimal('9999999999999999.99'):
            raise HTTPException(409, 'Tổng tiền vượt giới hạn giao dịch')
        with SessionLocal.begin() as db:
            payment = PaymentTransaction(payment_id=key, transaction_code='TXN-' + UUID(key).hex.upper(),
                request_hash=fingerprint, payer_user_id=principal.user_id, account_id=account['id'],
                payer_name=user['full_name'], payer_email=user['email'], mssv=data.mssv,
                student_name=snapshot['full_name'], selection_mode=data.selection_mode, total_amount=total,
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


@router.post('/{payment_id}/send-otp', response_model=OTPChallengeView, status_code=202)
def send_otp(payment_id: UUID, principal: Principal = Depends(require_principal), mailer: Mailer = Depends(get_mailer)):
    key = str(payment_id)
    load_payment(key, principal.user_id)
    with session_lock(engine, 'payment:' + key) as acquired:
        require_lock(acquired)
        with SessionLocal.begin() as db:
            payment = owned(db, key, principal.user_id)
            if payment.status not in {'PENDING_OTP', 'OTP_VERIFIED'}:
                raise HTTPException(409, 'Giao dịch không thể cấp OTP')
            now = utcnow()
            if payment.otp_last_sent_at is not None and (now - payment.otp_last_sent_at).total_seconds() < 60:
                raise HTTPException(429, 'Chờ 60 giây trước khi gửi lại OTP')
            code = generate_otp()
            payment.challenge_id = str(uuid4())
            payment.otp_expires_at = now + timedelta(minutes=5)
            payment.otp_last_sent_at = now
            payment.otp_verified_at = None
            payment.otp_attempts = 0
            payment.status = 'PENDING_OTP'
            payment.otp_hash = hash_otp(payment, code)
            local, _, domain = payment.payer_email.partition('@')
            result = OTPChallengeView(challenge_id=payment.challenge_id, expires_at=payment.otp_expires_at,
                delivery_address=(local[:1] + '***@' + domain) if domain else 'email đã đăng ký')
            subject, body = otp_message(payment, code)
            recipient, challenge_id = payment.payer_email, payment.challenge_id
        try:
            mailer.send(recipient=recipient, subject=subject, body=body, message_id=challenge_id)
        except MailError:
            with SessionLocal.begin() as db:
                failed = owned(db, key, principal.user_id)
                failed.otp_hash = failed.challenge_id = failed.otp_expires_at = failed.otp_last_sent_at = None
            raise HTTPException(503, 'Chưa gửi được OTP qua email. Vui lòng thử gửi lại.') from None
        return result


@router.post('/{payment_id}/verify-otp', response_model=OTPVerifiedView)
def verify_otp(payment_id: UUID, data: OTPVerifyRequest, principal: Principal = Depends(require_principal)):
    key = str(payment_id)
    with session_lock(engine, 'payment:' + key) as acquired:
        require_lock(acquired)
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
    load_payment(key, principal.user_id)
    result = process_payment(key, services)
    response.status_code = 200 if result.status == 'SUCCEEDED' else (409 if result.status in TERMINAL else 202)
    return result
