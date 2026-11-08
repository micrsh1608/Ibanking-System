"""Private stdout pipe for browser tests; generated IT credentials/codes stay in test memory."""
import json
import re
import sys
from decimal import Decimal

from tests.integration.backend_acceptance import new_student, new_user, AccountSession, TuitionSession, User, Student, Account
from tests.integration.mailpit import message_for


def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'email-info':
        message = message_for(sys.argv[2], receipt=len(sys.argv) > 3 and sys.argv[3] == 'receipt')
        print(json.dumps({'recipients': [item['Address'] for item in message['To']], 'subject': message['Subject']}))
        return
    if len(sys.argv)>1 and sys.argv[1]=='email-proof':
        message=message_for(sys.argv[2],email_verification=True)
        print(json.dumps({'code':re.search(r'Mã xác minh email của bạn:\s*(\d{6})',message['Text']).group(1)}))
        return
    if len(sys.argv) > 1 and sys.argv[1] == 'otp':
        message = message_for(sys.argv[2])
        print(json.dumps({'otp': re.search(r'Mã OTP của bạn:\s*(\d{6})', message['Text']).group(1)}))
        return
    user = new_user()
    scenario = sys.argv[2] if len(sys.argv)>2 and sys.argv[1]=='scenario' else 'normal'
    if scenario not in {'normal','zero-balance','exact-balance','missing-phone','locked','no-invoices','inactive','email-unverified'}:
        raise ValueError('Unknown synthetic UI scenario')
    mssv, ids = new_student([] if scenario=='no-invoices' else ['2000000.00', '3000000.00'])
    with AccountSession.begin() as db:
        profile = db.get(User, user['user_id'])
        profile.full_name, profile.identity_number, profile.phone = 'Nguyễn Minh An', '000000000099', '0900000099'
        if scenario=='missing-phone': profile.phone=None
        if scenario=='inactive': profile.is_active=False
        if scenario=='email-unverified': profile.email_verified_at=None
        account=db.get(Account,user['account_id'])
        if scenario=='zero-balance': account.balance=Decimal('0.00')
        if scenario=='exact-balance': account.balance=Decimal('5000000.00')
        if scenario=='locked': account.status='LOCKED'
    with TuitionSession.begin() as db:
        profile = db.query(Student).filter_by(mssv=mssv).one()
        profile.full_name = 'Nguyễn Hoàng Nam'
    print(json.dumps({name: user[name] for name in ('username', 'password')} | {'mssv': mssv, 'invoice_ids': ids}))


if __name__ == '__main__':
    main()
