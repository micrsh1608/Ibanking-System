from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Unicode,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    username: Mapped[str] = mapped_column(
        String(50), unique=True
    )
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(Unicode(100))
    identity_number: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )


class Account(Base):
    __tablename__ = "accounts"

    __table_args__ = (
        CheckConstraint(
            "balance >= 0",
            name="ck_accounts_balance",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'LOCKED')",
            name="ck_accounts_status",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), unique=True
    )
    account_number: Mapped[str] = mapped_column(
        String(30), unique=True
    )
    balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0.00")
    )
    status: Mapped[str] = mapped_column(
        String(10), default="ACTIVE"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )


class AccountEntry(Base):
    __tablename__ = "account_entries"

    __table_args__ = (
        UniqueConstraint(
            "payment_id",
            "entry_type",
            name="uq_payment_entry_type",
        ),
        CheckConstraint(
            "amount > 0",
            name="ck_entries_amount",
        ),
        CheckConstraint(
            "entry_type IN ('DEBIT', 'REFUND')",
            name="ck_entries_type",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    payment_id: Mapped[str] = mapped_column(String(36))
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id")
    )
    entry_type: Mapped[str] = mapped_column(String(10))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )