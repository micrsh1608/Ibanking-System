from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.otp import (
    SendOTPRequest,
    SendOTPResponse,
    VerifyOTPRequest,
    VerifyOTPResponse,
)
from app.services.otp_service import OTPService

router = APIRouter(prefix="/api/v1/otp", tags=["OTP"])


@router.post("/send", response_model=SendOTPResponse)
def send_otp(
    request: SendOTPRequest,
    db: Session = Depends(get_db),
):
    expires_in = OTPService.create_and_send(
        db=db,
        transaction_id=request.transaction_id,
        mssv=request.mssv,
        email=request.email,
    )

    return SendOTPResponse(
        transaction_id=request.transaction_id,
        message="OTP sent successfully",
        expires_in=expires_in,
    )


@router.post("/verify", response_model=VerifyOTPResponse)
def verify_otp(
    request: VerifyOTPRequest,
    db: Session = Depends(get_db),
):
    OTPService.verify(
        db=db,
        transaction_id=request.transaction_id,
        code=request.otp,
    )

    return VerifyOTPResponse(
        transaction_id=request.transaction_id,
        verified=True,
        message="OTP verified successfully",
    )
