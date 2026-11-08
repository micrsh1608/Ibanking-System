from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Unicode, UnicodeText, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from services.payment.database import Base
from shared.mailer import resolve_email_channel
from shared.time import utcnow


class PaymentTransaction(Base):
    __tablename__ = 'payments'
    __table_args__ = (
        CheckConstraint('total_amount > 0', name='ck_payment_total'),
        CheckConstraint("status IN ('PENDING_OTP','OTP_VERIFIED','PROCESSING','PENDING_RECONCILIATION','SUCCEEDED','FAILED','REFUNDED')", name='ck_payment_status'),
        Index('uq_payments_otp_fingerprint', 'otp_fingerprint', unique=True,
            mssql_where=text('otp_fingerprint IS NOT NULL'), sqlite_where=text('otp_fingerprint IS NOT NULL')),
    )

    payment_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    transaction_code: Mapped[str] = mapped_column(String(40), unique=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    payer_user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    account_id: Mapped[int] = mapped_column(BigInteger)
    payer_name: Mapped[str] = mapped_column(Unicode(150))
    payer_email: Mapped[str] = mapped_column(String(255))
    email_channel: Mapped[str] = mapped_column(String(12), default='smtp', server_default='smtp')
    mssv: Mapped[str] = mapped_column(String(24))
    student_name: Mapped[str] = mapped_column(Unicode(150))
    selection_mode: Mapped[str] = mapped_column(String(16))
    terms_version: Mapped[str | None] = mapped_column(String(32))
    terms_accepted_at: Mapped[datetime | None] = mapped_column(DateTime)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    status: Mapped[str] = mapped_column(String(32), default='PENDING_OTP', index=True)
    phase: Mapped[str] = mapped_column(String(16), default='RESERVE')
    error_message: Mapped[str | None] = mapped_column(UnicodeText)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    challenge_id: Mapped[str | None] = mapped_column(String(36))
    otp_hash: Mapped[str | None] = mapped_column(String(64))
    otp_fingerprint: Mapped[str | None] = mapped_column(String(64))
    otp_expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    otp_last_sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    otp_verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    otp_attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    items: Mapped[list['PaymentItem']] = relationship(back_populates='payment', order_by='PaymentItem.invoice_id', lazy='selectin')
    notifications: Mapped[list['EmailOutbox']] = relationship(lazy='selectin')

    @property
    def email_delivery(self):
        return resolve_email_channel(self.email_channel or 'configured')

    @property
    def receipt_status(self):
        return next((row.status for row in self.notifications if row.event_type == 'PAYMENT_SUCCEEDED'), None)

    @property
    def active_challenge(self):
        if self.status != 'PENDING_OTP' or not all((self.otp_hash, self.challenge_id, self.otp_expires_at)):
            return None
        local, _, domain = self.payer_email.partition('@')
        cooldown = max(0, 60 - int((utcnow() - self.otp_last_sent_at).total_seconds())) if self.otp_last_sent_at else 0
        return {'challenge_id': self.challenge_id, 'expires_at': self.otp_expires_at,
            'resend_after_seconds': cooldown, 'demo_mode': False,
            'email_delivery': self.email_delivery,
            'delivery_address': (local[:1] + '***@' + domain) if domain else 'email đã đăng ký'}


class PaymentItem(Base):
    __tablename__ = 'payment_items'
    __table_args__ = (
        UniqueConstraint('payment_id', 'invoice_id', name='uq_payment_invoice'),
        CheckConstraint('amount > 0', name='ck_payment_item_amount'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payment_id: Mapped[str] = mapped_column(ForeignKey('payments.payment_id'), index=True)
    invoice_id: Mapped[int] = mapped_column(Integer)
    invoice_version: Mapped[int] = mapped_column(Integer)
    semester: Mapped[str] = mapped_column(String(32))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    payment: Mapped[PaymentTransaction] = relationship(back_populates='items')


class EmailOutbox(Base):
    __tablename__ = 'email_outbox'
    __table_args__ = (
        UniqueConstraint('payment_id', 'event_type', name='uq_outbox_payment_event'),
        CheckConstraint("status IN ('PENDING','SENT')", name='ck_outbox_status'),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    payment_id: Mapped[str] = mapped_column(ForeignKey('payments.payment_id'), index=True)
    event_type: Mapped[str] = mapped_column(String(32))
    recipient: Mapped[str] = mapped_column(String(255))
    email_channel: Mapped[str] = mapped_column(String(12), default='smtp', server_default='smtp')
    subject: Mapped[str] = mapped_column(Unicode(255))
    body: Mapped[str] = mapped_column(UnicodeText)
    status: Mapped[str] = mapped_column(String(12), default='PENDING')
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(80))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
