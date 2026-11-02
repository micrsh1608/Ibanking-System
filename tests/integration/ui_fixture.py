"""Private stdout pipe for browser tests; generated IT credentials/codes stay in test memory."""
import json
import re
import sys

from tests.integration.backend_acceptance import new_student, new_user, AccountSession, TuitionSession, User, Student
from tests.integration.mailpit import message_for


def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'otp':
        message = message_for(sys.argv[2])
        print(json.dumps({'otp': re.search(r'Mã OTP của bạn:\s*(\d{6})', message['Text']).group(1)}))
        return
    user = new_user()
    mssv, ids = new_student(['2000000.00', '3000000.00'])
    with AccountSession.begin() as db:
        profile = db.get(User, user['user_id'])
        profile.full_name, profile.identity_number, profile.phone = 'Nguyễn Minh An', '000000000099', '0900000099'
    with TuitionSession.begin() as db:
        profile = db.query(Student).filter_by(mssv=mssv).one()
        profile.full_name = 'Nguyễn Hoàng Nam'
    print(json.dumps({name: user[name] for name in ('username', 'password')} | {'mssv': mssv, 'invoice_ids': ids}))


if __name__ == '__main__':
    main()
