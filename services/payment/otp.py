import hashlib
import hmac
import os
import secrets


def generate_otp():
    return f'{secrets.randbelow(1_000_000):06d}'


def hash_otp(payment, otp):
    items = ','.join(f'{item.invoice_id}:{item.invoice_version}:{item.amount:.2f}' for item in payment.items)
    binding = f'{payment.payment_id}:{payment.challenge_id}:{payment.total_amount:.2f}:{items}:{otp}'
    return hmac.new(os.environ['JWT_SECRET_KEY'].encode(), binding.encode(), hashlib.sha256).hexdigest()
