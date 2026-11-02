from decimal import Decimal

from pwdlib import PasswordHash
from sqlalchemy import select

from services.account.database import Base, engine, SessionLocal
from services.account.models import User, Account, AccountEntry


password_hasher = PasswordHash.recommended()


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
                email="huy@example.com",
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
