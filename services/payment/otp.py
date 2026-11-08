import hashlib
import hmac
import os
import secrets

from fastapi import HTTPException
from sqlalchemy import select, update
from shared.locking import transaction_lock


def generate_otp():
    return f'{secrets.randbelow(1_000_000):06d}'


def hash_otp(payment, otp):
    items = ','.join(f'{item.invoice_id}:{item.invoice_version}:{item.amount:.2f}' for item in payment.items)
    binding = f'{payment.payment_id}:{payment.challenge_id}:{payment.total_amount:.2f}:{items}:{otp}'
    return hmac.new(os.environ['JWT_SECRET_KEY'].encode(), binding.encode(), hashlib.sha256).hexdigest()


def code_fingerprint(otp):
    """Stable, secret-keyed equality token; no plaintext six-digit code is stored."""
    return hmac.new(os.environ['JWT_SECRET_KEY'].encode(), ('otp-active-code:v1:' + otp).encode(), hashlib.sha256).hexdigest()


def allocate_code(db, payment, now, generate):
    from services.payment.models.payment import PaymentTransaction
    # All instances serialize allocation in payment_db. No SMTP runs while this
    # transaction lock is held; the filtered unique index is a second guard.
    transaction_lock(db, 'otp:active-code-allocation')
    previous = payment.otp_fingerprint
    db.execute(update(PaymentTransaction).where(PaymentTransaction.otp_fingerprint.is_not(None),
        PaymentTransaction.otp_expires_at <= now).values(otp_fingerprint=None))
    for _ in range(128):
        code = generate()
        fingerprint = code_fingerprint(code)
        if fingerprint == previous:
            continue
        if db.scalar(select(PaymentTransaction.payment_id).where(PaymentTransaction.otp_fingerprint == fingerprint)) is None:
            payment.otp_fingerprint = fingerprint
            return code
    raise HTTPException(503, 'Chưa cấp được mã OTP duy nhất. Vui lòng thử lại sau.')
