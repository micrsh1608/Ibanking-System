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

from services.account.database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("email_channel IN ('configured','smtp','mailpit')", name='ck_user_email_channel'),
    )

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
    email_channel: Mapped[str] = mapped_column(String(12), default='smtp', server_default='smtp')
    phone: Mapped[str | None] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    pending_email: Mapped[str | None] = mapped_column(String(255))
    email_challenge_id: Mapped[str | None] = mapped_column(String(36))
    email_code_hash: Mapped[str | None] = mapped_column(String(64))
    email_code_expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    email_code_sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    email_code_attempts: Mapped[int] = mapped_column(default=0, server_default='0')
    email_pending_profile: Mapped[str | None] = mapped_column(Unicode(2000))
    email_pending_channel: Mapped[str | None] = mapped_column(String(12))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    @property
    def email_verified(self):
        return self.email_verified_at is not None

    @property
    def email_delivery(self):
        from shared.mailer import resolve_email_channel
        return resolve_email_channel(self.email_channel or 'configured')

    @property
    def email_verification(self):
        from shared.time import utcnow
        if not all((self.pending_email, self.email_challenge_id, self.email_code_hash, self.email_code_expires_at)):
            return None
        local, _, domain = self.pending_email.partition('@')
        return {'challenge_id': self.email_challenge_id, 'expires_at': self.email_code_expires_at,
            'resend_after_seconds': max(0, 60-int((utcnow()-self.email_code_sent_at).total_seconds())) if self.email_code_sent_at else 0,
            'delivery_address': local[:1]+'***@'+domain}


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


class AccountCancellation(Base):
    """Permanent fence: cancellation wins even if the original debit arrives later."""
    __tablename__ = "account_cancellations"
    __table_args__ = (CheckConstraint('amount > 0', name='ck_cancellation_amount'),)

    payment_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey('accounts.id'))
    payer_user_id: Mapped[int] = mapped_column(BigInteger)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
