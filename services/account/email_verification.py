"""Email ownership proof, separate from financial transaction OTP challenges."""
import hashlib
import hmac
import json
import os
import secrets
from datetime import timedelta
from uuid import uuid4

from fastapi import HTTPException
from shared.mailer import MailError
from shared.time import utcnow


def generate_code():
    return f'{secrets.randbelow(1_000_000):06d}'


def hash_code(user, code):
    value=f'email-ownership:v1:{user.id}:{user.email_challenge_id}:{user.pending_email}:{user.email_pending_profile}:{code}'
    pending_channel = getattr(user, 'email_pending_channel', None)
    if pending_channel:
        value += ':channel:' + pending_channel
    return hmac.new(os.environ['JWT_SECRET_KEY'].encode(),value.encode(),hashlib.sha256).hexdigest()


def clear_pending(user):
    user.pending_email=user.email_challenge_id=user.email_code_hash=None
    user.email_code_expires_at=user.email_pending_profile=None
    user.email_pending_channel=None
    user.email_code_attempts=0


def stage(user, profile):
    now=utcnow()
    if user.email_code_sent_at and (now-user.email_code_sent_at).total_seconds()<60:
        raise HTTPException(429,'Chờ 60 giây trước khi yêu cầu mã xác minh email mới.')
    for _ in range(128):
        code=generate_code()
        if not user.email_code_hash or not hmac.compare_digest(user.email_code_hash,hash_code(user,code)):
            break
    else:
        raise HTTPException(503,'Chưa cấp được mã xác minh mới. Vui lòng thử lại.')
    user.pending_email=profile['email']
    user.email_pending_profile=json.dumps(profile,ensure_ascii=False,sort_keys=True)
    delivery = user.email_delivery
    user.email_pending_channel = delivery if delivery == 'smtp' else None
    user.email_challenge_id=str(uuid4())
    user.email_code_expires_at=now+timedelta(minutes=5)
    user.email_code_sent_at=now
    user.email_code_attempts=0
    user.email_code_hash=hash_code(user,code)
    return {'recipient':user.pending_email,'subject':f'iBanking — Xác minh email {user.email_challenge_id}',
        'body':f'Mã xác minh email của bạn: {code}\n\nMã yêu cầu: {user.email_challenge_id}\n'
            'Mã có hiệu lực tối đa 5 phút và chỉ dùng một lần để xác minh địa chỉ email này.\n'
            'Đây là mã xác minh hồ sơ, không phải OTP thanh toán học phí.\n'
            'Email và thông tin hồ sơ chỉ được lưu sau khi bạn xác minh thành công.\n',
        'message_id':user.email_challenge_id, 'channel':user.email_channel or 'configured'}


def deliver_or_revoke(user_id, message, mailer):
    from services.account.database import SessionLocal
    from services.account.models import User
    try:
        mailer.send(**message)
    except MailError:
        with SessionLocal.begin() as db:
            user=db.get(User,user_id)
            if user.email_challenge_id==message['message_id']:
                clear_pending(user)
        raise HTTPException(503,'Chưa gửi được mã xác minh email. Hồ sơ và email đang dùng chưa thay đổi.') from None
