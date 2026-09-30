from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.otp import OTP
from app.models.student import Student
from app.services.email_service import EmailService
from app.utils.otp import generate_otp


class OTPService:

    @staticmethod
    def create_and_send(
        db: Session,
        transaction_id: str,
        mssv: str,
        email: str,
    ) -> int:
        student = db.scalar(select(Student).where(Student.mssv == mssv))

        if student is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Student not found",
            )

        if student.email.lower() != email.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email does not match student information",
            )

        # Do not create a second active OTP for the same transaction.
        now = datetime.utcnow()
        existing = db.scalar(
            select(OTP)
            .where(
                OTP.transaction_id == transaction_id,
                OTP.used.is_(False),
                OTP.expires_at > now,
            )
            .order_by(OTP.created_at.desc())
        )

        if existing:
            # Re-send the existing active OTP.
            EmailService().send_otp(
                email,
                existing.otp_code,
                transaction_id,
                max(0, int((existing.expires_at - now).total_seconds())),
            )
            return max(0, int((existing.expires_at - now).total_seconds()))

        # Generate an OTP that is not equal to any active OTP.
        for _ in range(20):
            code = generate_otp(settings.otp_length)
            duplicate = db.scalar(
                select(OTP.id).where(
                    OTP.otp_code == code,
                    OTP.used.is_(False),
                    OTP.expires_at > now,
                )
            )
            if duplicate is None:
                break
        else:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Cannot generate a unique OTP right now",
            )

        expires_at = now + timedelta(minutes=settings.otp_expire_minutes)

        otp = OTP(
            transaction_id=transaction_id,
            mssv=mssv,
            email=email,
            otp_code=code,
            expires_at=expires_at,
            used=False,
        )

        db.add(otp)
        db.commit()

        EmailService().send_otp(
            email,
            code,
            transaction_id,
            settings.otp_expire_minutes * 60,
        )

        return settings.otp_expire_minutes * 60

    @staticmethod
    def verify(db: Session, transaction_id: str, code: str) -> None:
        now = datetime.utcnow()

        otp = db.scalar(
            select(OTP)
            .where(
                OTP.transaction_id == transaction_id,
                OTP.used.is_(False),
            )
            .order_by(OTP.created_at.desc())
        )

        if otp is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="OTP not found or already used",
            )

        if now > otp.expires_at:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="OTP expired",
            )

        if otp.otp_code != code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid OTP",
            )

        # Atomic one-time use.
        stmt = (
            update(OTP)
            .where(
                OTP.id == otp.id,
                OTP.used.is_(False),
            )
            .values(used=True)
        )

        result = db.execute(stmt)

        if result.rowcount != 1:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="OTP has already been used",
            )

        db.commit()
