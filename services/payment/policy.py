"""Rules applied before accepting a new full-tuition payment intent."""
import re
from fastapi import HTTPException

TERMS_VERSION = '2026-11-03'


def validate_payer(user):
    if user.get('email_verified') is not True:
        raise HTTPException(409, 'Cần xác minh email trong Thông tin cá nhân trước khi thanh toán')
    if not str(user.get('full_name') or '').strip():
        raise HTTPException(409, 'Bổ sung họ tên trong Thông tin cá nhân trước khi thanh toán')
    if not re.fullmatch(r'[^\s@<>\x00-\x1f\x7f]+@[^\s@<>\x00-\x1f\x7f]+\.[^\s@<>\x00-\x1f\x7f]+', str(user.get('email') or '')):
        raise HTTPException(409, 'Bổ sung email hợp lệ trong Thông tin cá nhân trước khi thanh toán')
    phone = str(user.get('phone') or '')
    if not re.fullmatch(r'[+0-9 ()-]{7,20}', phone) or not 7 <= len(re.sub(r'\D', '', phone)) <= 15:
        raise HTTPException(409, 'Bổ sung số điện thoại hợp lệ trong Thông tin cá nhân trước khi thanh toán')


def is_legacy_draft(payment):
    return payment.status in {'PENDING_OTP', 'OTP_VERIFIED'} and (
        payment.selection_mode != 'ALL_UNPAID' or payment.terms_accepted_at is None)
