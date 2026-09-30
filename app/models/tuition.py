from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Tuition(Base):
    __tablename__ = "tuitions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id"),
        unique=True,
        nullable=False,
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="UNPAID")
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    paid_transaction_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    student = relationship("Student", back_populates="tuition")
