"""Idempotent Account seed data; existing profiles and money are never reset."""
import re
from decimal import Decimal

from pwdlib import PasswordHash
from sqlalchemy import func, select

from services.account.database import SessionLocal
from services.account.models import User, Account


password_hasher = PasswordHash.recommended()
DEMO_PASSWORD = 'Demo_123!'
DEMO_INITIAL_BALANCE = Decimal('10000000.00')
TEST_ACCOUNT_PASSWORD = 'HuyDemo_123!'
EMAIL = re.compile(r'^[^\s@<>\x00-\x1f\x7f]+@[^\s@<>\x00-\x1f\x7f]+\.[^\s@<>\x00-\x1f\x7f]+$')


class DemoSeedError(ValueError):
    pass


def demo_account_plan(environ=None):
    """Recipients are entered and verified by each user, never inferred from SMTP."""
    return [dict(username=f'demo{index:02d}', account_number=f'DEMO{10000000 + index}',
                 full_name=f'Demo {index:02d}', email='', email_channel='smtp',
                 phone=f'0901{index:06d}', identity_number=str(100000000000 + index))
            for index in range(1, 11)]


def seed_demo_accounts(session_factory=None, *, environ=None):
    """Create missing catalog accounts only; inbox proof remains an Account API action."""
    factory = session_factory or SessionLocal
    plan = demo_account_plan(environ)
    users = []
    with factory.begin() as db:
        owned = []
        for item in plan:
            user = db.scalar(select(User).where(func.lower(User.username) == item['username']))
            account = db.scalar(select(Account).where(Account.user_id == user.id)) if user else None
            by_number = db.scalar(select(Account).where(Account.account_number == item['account_number']))
            if user and (user.username != item['username'] or account is None or account.account_number != item['account_number']):
                raise DemoSeedError('An existing demo username is not owned by this catalog; no account was overwritten.')
            if by_number is not None and (user is None or by_number.user_id != user.id):
                raise DemoSeedError('A catalog account number is already owned by another user.')
            owned.append((item, user, account))
        hashed = password_hasher.hash(DEMO_PASSWORD) if any(user is None for _, user, _ in owned) else None
        for item, user, account in owned:
            created = user is None
            if created:
                user = User(**{key: value for key, value in item.items() if key != 'account_number'},
                            password_hash=hashed, is_active=True)
                db.add(user)
                db.flush()
                account = Account(user_id=user.id, account_number=item['account_number'],
                                  balance=DEMO_INITIAL_BALANCE, status='ACTIVE')
                db.add(account)
                db.flush()
            users.append({'username': user.username, 'user_id': user.id, 'account_id': account.id,
                          'account_number': account.account_number, 'balance': format(account.balance, '.2f'),
                          'account_status': account.status, 'email': user.email, 'email_channel': user.email_channel,
                          'email_verified': user.email_verified, 'created': created})
    return users


def create_test_account(username='huy2', email='', session_factory=None):
    """Create the second local test payer; never rewrite an existing profile or money."""
    if not re.fullmatch(r'[a-z][a-z0-9_]{2,49}', username):
        raise DemoSeedError('Use a lowercase test username of 3-50 letters, digits or underscores.')
    email = email.strip()
    if email and (len(email) > 255 or not EMAIL.fullmatch(email)):
        raise DemoSeedError('Enter a valid email address, or leave it empty for entry on the profile screen.')
    factory = session_factory or SessionLocal
    number = '1000000002'
    with factory.begin() as db:
        user = db.scalar(select(User).where(func.lower(User.username) == username))
        account = db.scalar(select(Account).where(Account.user_id == user.id)) if user else None
        by_number = db.scalar(select(Account).where(Account.account_number == number))
        if user and (user.username != username or account is None or account.account_number != number):
            raise DemoSeedError('The test username already belongs to another account; nothing was overwritten.')
        if by_number is not None and (user is None or by_number.user_id != user.id):
            raise DemoSeedError('Account number 1000000002 is already owned by another user.')
        created = user is None
        if created:
            user = User(username=username, password_hash=password_hasher.hash(TEST_ACCOUNT_PASSWORD),
                full_name='Nguyễn Minh Nam', email=email, email_channel='smtp',
                phone='0900000002', identity_number='000000000002', is_active=True)
            db.add(user)
            db.flush()
            account = Account(user_id=user.id, account_number=number,
                balance=DEMO_INITIAL_BALANCE, status='ACTIVE')
            db.add(account)
            db.flush()
        return {'status': 'CREATED' if created else 'PRESERVED', 'created': created,
            'username': user.username, 'user_id': user.id, 'account_id': account.id,
            'account_number': account.account_number, 'balance': format(account.balance, '.2f'),
            'account_status': account.status, 'email': user.email, 'email_channel': user.email_channel,
            'email_verified': user.email_verified, 'verification': 'manual_on_profile',
            'initial_password': TEST_ACCOUNT_PASSWORD if created else None,
            'note': 'Verify the email in Personal information before paying. Existing profiles, passwords and balances are preserved.'}


def init_db():
    from services.account.migrate import migrate
    migrate()

    with SessionLocal.begin() as db:
        user = db.scalar(
            select(User).where(User.username == "huy")
        )

        if user is None:
            user = User(
                username="huy",
                password_hash=password_hasher.hash("HuyDemo_123!"),
                full_name="Phạm Minh Huy",
                email="",
                email_channel="smtp",
                identity_number="000000000001",
                phone="0900000001",
                is_active=True,
            )
            db.add(user)
            db.flush()

        account = db.scalar(
            select(Account).where(Account.user_id == user.id)
        )

        if account is None:
            account = Account(
                user_id=user.id,
                account_number="1000000001",
                balance=Decimal("10000000.00"),
                status="ACTIVE",
            )
            db.add(account)

    print("Đã tạo bảng và chuẩn bị dữ liệu mẫu.")


if __name__ == "__main__":
    init_db()
