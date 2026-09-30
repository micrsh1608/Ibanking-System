from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class OTP(Base):
    __tablename__ = "otps"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    transaction_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    mssv: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    otp_code: Mapped[str] = mapped_column(String(20), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_otp_transaction_created", "transaction_id", "created_at"),
    )
