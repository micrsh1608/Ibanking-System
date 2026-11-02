"""Durable reserve/debit/finalize saga. All network calls happen outside SQL transactions."""
from datetime import timedelta
from decimal import Decimal

from fastapi import HTTPException

from services.payment.clients import Services, UpstreamError
from services.payment.database import SessionLocal, engine
from services.payment.models.payment import PaymentTransaction
from services.payment.schemas import PaymentView
from shared.locking import session_lock
from shared.time import utcnow

TERMINAL = {'SUCCEEDED', 'FAILED', 'REFUNDED'}


def load_payment(payment_id, user_id=None):
    with SessionLocal() as db:
        row = db.get(PaymentTransaction, str(payment_id))
        if row is None or (user_id is not None and row.payer_user_id != user_id):
            raise HTTPException(404, 'Không tìm thấy giao dịch')
        return row


def payment_view(payment_id, user_id=None):
    return PaymentView.model_validate(load_payment(payment_id, user_id))


def update(payment_id, **fields):
    with SessionLocal.begin() as db:
        row = db.get(PaymentTransaction, payment_id)
        for field, value in fields.items():
            setattr(row, field, value)


def validate_operation(payment, result, statuses):
    if (result.get('payment_id') != payment.payment_id or result.get('account_id') != payment.account_id
            or Decimal(result.get('amount', '0')) != payment.total_amount or result.get('status') not in statuses):
        raise UpstreamError(503, 'Account trả kết quả không khớp giao dịch')


def validate_reservation(payment, result):
    if (result.get('payment_id') != payment.payment_id or result.get('mssv') != payment.mssv
            or set(result.get('invoice_ids', [])) != {item.invoice_id for item in payment.items}
            or Decimal(result.get('total_amount', '0')) != payment.total_amount
            or result.get('status') not in {'RESERVED', 'PAID'}):
        raise UpstreamError(503, 'Tuition trả kết quả không khớp nhóm hóa đơn')


def succeeded(payment_id):
    from services.payment.outbox import enqueue_receipt
    with SessionLocal.begin() as db:
        payment = db.get(PaymentTransaction, payment_id)
        payment.status, payment.phase = 'SUCCEEDED', 'DONE'
        payment.error_message, payment.next_retry_at = None, None
        payment.completed_at = payment.completed_at or utcnow()
        enqueue_receipt(db, payment)


def defer(payment, error):
    attempts = payment.retry_count + 1
    update(payment.payment_id, status='PENDING_RECONCILIATION', retry_count=attempts,
        error_message=error.detail[:1000], next_retry_at=utcnow() + timedelta(seconds=min(60, 2 ** min(attempts, 5))))


def process_payment(payment_id, services=None):
    key = str(payment_id)
    services = services or Services()
    with session_lock(engine, 'payment:' + key) as acquired:
        if not acquired:
            return payment_view(key)
        payment = load_payment(key)
        if payment.status in TERMINAL:
            return PaymentView.model_validate(payment)
        if payment.status == 'PENDING_OTP':
            raise HTTPException(409, 'Cần xác minh OTP trước khi xử lý')
        if payment.status == 'OTP_VERIFIED':
            if payment.otp_expires_at is None or payment.otp_expires_at <= utcnow():
                raise HTTPException(409, 'Xác minh OTP đã hết hạn; yêu cầu mã mới')
            # Commit the user's processing intent before any remote side effect.
            update(key, status='PROCESSING', phase='RESERVE', next_retry_at=None)

        for _ in range(5):
            payment = load_payment(key)
            try:
                if payment.phase == 'RESERVE':
                    try:
                        result = services.reserve(payment)
                        validate_reservation(payment, result)
                    except UpstreamError as error:
                        if error.status not in {403, 404, 409, 422}:
                            raise
                        update(key, status='PROCESSING', phase='CANCEL', error_message=error.detail)
                        continue
                    update(key, status='PROCESSING', phase='DEBIT', error_message=None)
                elif payment.phase == 'DEBIT':
                    try:
                        result = services.account(payment, 'debit')
                        validate_operation(payment, result, {'DEBITED', 'REFUNDED', 'CANCELLED'})
                    except UpstreamError as error:
                        if error.status not in {403, 404, 409, 422}:
                            raise
                        update(key, status='PROCESSING', phase='CANCEL', error_message=error.detail)
                        continue
                    if result['status'] != 'DEBITED':
                        update(key, status='PROCESSING', phase='CANCEL', error_message='Khoản trừ tiền đã hủy/hoàn')
                        continue
                    update(key, status='PROCESSING', phase='FINALIZE', error_message=None)
                elif payment.phase == 'FINALIZE':
                    try:
                        result = services.reservation(key, 'finalize')
                        validate_reservation(payment, result)
                        if result['status'] != 'PAID':
                            raise UpstreamError(503, 'Chưa xác nhận hoàn tất hóa đơn')
                    except UpstreamError as error:
                        if error.status != 409:
                            raise
                        update(key, status='PROCESSING', phase='CANCEL', error_message=error.detail)
                        continue
                    succeeded(key)
                    break
                elif payment.phase == 'CANCEL':
                    # Fence finalize BEFORE refunding. PAID must never be refunded here.
                    try:
                        released = services.reservation(key, 'release')
                    except UpstreamError as error:
                        if error.status != 409:
                            raise
                        current = services.reservation(key)
                        validate_reservation(payment, current)
                        if current['status'] != 'PAID':
                            raise UpstreamError(503, 'Chưa thể nhả nhóm hóa đơn')
                        operation = services.operation(key)
                        validate_operation(payment, operation, {'DEBITED'})
                        succeeded(key)
                        break
                    if released.get('payment_id') != key or released.get('status') != 'RELEASED':
                        raise UpstreamError(503, 'Chưa xác nhận hủy nhóm hóa đơn')
                    operation = services.account(payment, 'cancel')
                    validate_operation(payment, operation, {'CANCELLED', 'REFUNDED'})
                    update(key, status='REFUNDED' if operation['status'] == 'REFUNDED' else 'FAILED',
                        phase='DONE', next_retry_at=None)
                    break
                else:
                    raise UpstreamError(503, 'Bước xử lý không hợp lệ; cần đối soát')
            except UpstreamError as error:
                defer(payment, error)
                break
            except (ValueError, KeyError, TypeError):
                defer(payment, UpstreamError(503, 'Phản hồi service không hợp lệ; cần đối soát'))
                break
        return payment_view(key)
