from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.student import Student
from app.models.tuition import Tuition


class TuitionService:

    @staticmethod
    def get_by_mssv(db: Session, mssv: str) -> Tuition:
        stmt = (
            select(Tuition)
            .join(Student, Tuition.student_id == Student.id)
            .where(Student.mssv == mssv)
        )
        tuition = db.scalar(stmt)

        if tuition is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Student or tuition not found",
            )

        return tuition

    @staticmethod
    def mark_paid(db: Session, mssv: str, transaction_id: str) -> Tuition:
        # Atomic state transition:
        # only UNPAID -> PAID is allowed.
        tuition = TuitionService.get_by_mssv(db, mssv)

        if tuition.status == "PAID":
            if tuition.paid_transaction_id == transaction_id:
                return tuition

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Tuition has already been paid",
            )

        stmt = (
            update(Tuition)
            .where(
                Tuition.id == tuition.id,
                Tuition.status == "UNPAID",
            )
            .values(
                status="PAID",
                paid_at=datetime.utcnow(),
                paid_transaction_id=transaction_id,
            )
        )

        result = db.execute(stmt)

        if result.rowcount != 1:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Tuition was updated by another transaction",
            )

        db.commit()
        db.refresh(tuition)
        return tuition
