from decimal import Decimal

from pwdlib import PasswordHash
from sqlalchemy import select

from app.database import Base, engine, SessionLocal
from app.models import User, Account, AccountEntry


password_hasher = PasswordHash.recommended()


def init_db():
    Base.metadata.create_all(bind=engine)

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