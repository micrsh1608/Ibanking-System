from sqlalchemy import Column, Integer, String, Numeric

from app.db.database import Base


class TuitionFee(Base):
    __tablename__ = "tuition_fees"

    id = Column(Integer, primary_key=True, index=True)

    student_id = Column(
        Integer,
        unique=True,
        nullable=False
    )

    student_name = Column(
        String(100),
        nullable=False
    )

    amount_due = Column(
        Numeric(15, 2),
        nullable=False
    )

    status = Column(
        String(20),
        nullable=False,
        default="UNPAID"
    )