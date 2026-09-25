from datetime import datetime
from decimal import Decimal

from sqlalchemy import Column, Integer, String, Numeric, DateTime, Text

from app.db.database import Base

class PaymentTransaction(Base):
    __tablename__ = "payment_transactions"

    id = Column(Integer, primary_key=True, index=True)

    transaction_code = Column(
        String(50),
        unique=True,
        nullable=False,
        index=True
    )

    payer_id = Column(Integer, nullable=False)

    student_id = Column(Integer, nullable=False)

    amount = Column(
        Numeric(15, 2),
        nullable=False
    )

    status = Column(
        String(20),
        nullable=False,
        default="PENDING"
    )

    otp_verified = Column(
        String(10),
        nullable=False,
        default="NO"
    )
    
    otp_hash = Column(
    String(255),
    nullable=True
    )

    otp_expires_at = Column(
        DateTime,
        nullable=True
    )

    otp_attempts = Column(
        Integer,
        nullable=False,
        default=0
    )

    error_message = Column(Text, nullable=True)

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )