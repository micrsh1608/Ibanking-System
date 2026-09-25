from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timezone

from app.db.database import get_db
from app.models.payment import PaymentTransaction
from app.models.account import Account
from app.models.tuition import TuitionFee
from app.schemas.payment import (
    PaymentCreate,
    PaymentResponse,
    PaymentValidationRequest,
    PaymentValidationResponse,
    OTPVerifyRequest,
    OTPVerifyResponse,
    PaymentProcessResponse
)
from app.services.otp_service import (
    generate_otp,
    hash_otp,
    get_otp_expiry
)

router = APIRouter(
    prefix="/api/v1/payments",
    tags=["Payments"]
)

@router.post(
    "",
    response_model=PaymentResponse,
    status_code=201
)
def create_payment(
    payment: PaymentCreate,
    db: Session = Depends(get_db)
):
    transaction = PaymentTransaction(
        transaction_code=f"TXN-{uuid4().hex[:12].upper()}",
        payer_id=payment.payer_id,
        student_id=payment.student_id,
        amount=payment.amount,
        status="PENDING",
        otp_verified="NO"
    )

    db.add(transaction)
    db.commit()
    db.refresh(transaction)

    return transaction

@router.get(
    "/history/{payer_id}",
    response_model=list[PaymentResponse]
)
def get_payment_history(
    payer_id: int,
    db: Session = Depends(get_db)
):
    transactions = (
        db.query(PaymentTransaction)
        .filter(
            PaymentTransaction.payer_id == payer_id
        )
        .order_by(
            PaymentTransaction.created_at.desc()
        )
        .all()
    )

    return transactions

@router.post(
    "/validate",
    response_model=PaymentValidationResponse
)
def validate_payment(
    data: PaymentValidationRequest,
    db: Session = Depends(get_db)
):
    account = (
        db.query(Account)
        .filter(Account.id == data.payer_id)
        .first()
    )

    if account is None:
        raise HTTPException(
            status_code=404,
            detail="Account not found"
        )

    tuition = (
        db.query(TuitionFee)
        .filter(
            TuitionFee.student_id == data.student_id
        )
        .first()
    )

    if tuition is None:
        raise HTTPException(
            status_code=404,
            detail="Tuition fee not found"
        )

    if tuition.status == "PAID":
        raise HTTPException(
            status_code=400,
            detail="Tuition fee already paid"
        )

    sufficient_balance = account.balance >= tuition.amount_due

    if not sufficient_balance:
        message = "Insufficient balance"
    else:
        message = "Payment validation successful"

    return PaymentValidationResponse(
        payer_id=data.payer_id,
        student_id=data.student_id,
        balance=account.balance,
        amount_due=tuition.amount_due,
        sufficient_balance=sufficient_balance,
        tuition_status=tuition.status,
        message=message
    )

@router.get("/{transaction_code}", response_model=PaymentResponse)
def get_payment(
    transaction_code: str,
    db: Session = Depends(get_db)
):
    transaction = (
        db.query(PaymentTransaction)
        .filter(
            PaymentTransaction.transaction_code == transaction_code
        )
        .first()
    )

    if transaction is None:
        raise HTTPException(
            status_code=404,
            detail="Transaction not found"
        )

    return transaction

@router.post(
    "/{transaction_code}/send-otp"
)
def send_otp(
    transaction_code: str,
    db: Session = Depends(get_db)
):
    transaction = (
        db.query(PaymentTransaction)
        .filter(
            PaymentTransaction.transaction_code
            == transaction_code
        )
        .first()
    )

    if transaction is None:
        raise HTTPException(
            status_code=404,
            detail="Transaction not found"
        )

    if transaction.status != "PENDING":
        raise HTTPException(
            status_code=400,
            detail="Transaction cannot request OTP"
        )

    otp = generate_otp()

    transaction.otp_hash = hash_otp(otp)
    transaction.otp_expires_at = get_otp_expiry()
    transaction.otp_attempts = 0

    db.commit()
    db.refresh(transaction)

    print(f"[MOCK OTP] {transaction_code}: {otp}")

    return {
        "transaction_code": transaction_code,
        "message": "OTP generated successfully",
        "expires_in_minutes": 5
    }

@router.post(
    "/{transaction_code}/verify-otp",
    response_model=OTPVerifyResponse
)
def verify_otp(
    transaction_code: str,
    data: OTPVerifyRequest,
    db: Session = Depends(get_db)
):
    transaction = (
        db.query(PaymentTransaction)
        .filter(
            PaymentTransaction.transaction_code == transaction_code
        )
        .first()
    )

    if transaction is None:
        raise HTTPException(
            status_code=404,
            detail="Transaction not found"
        )

    if transaction.status != "PENDING":
        raise HTTPException(
            status_code=400,
            detail="Transaction cannot verify OTP"
        )

    if transaction.otp_hash is None:
        raise HTTPException(
            status_code=400,
            detail="OTP has not been requested"
        )

    if transaction.otp_expires_at is None:
        raise HTTPException(
            status_code=400,
            detail="OTP expiration time is missing"
        )

    if datetime.now(timezone.utc).replace(tzinfo=None) > transaction.otp_expires_at:
        raise HTTPException(
            status_code=400,
            detail="OTP has expired"
        )

    if transaction.otp_attempts >= 5:
        raise HTTPException(
            status_code=400,
            detail="Too many invalid OTP attempts"
        )

    if hash_otp(data.otp) != transaction.otp_hash:
        transaction.otp_attempts += 1
        db.commit()

        raise HTTPException(
            status_code=400,
            detail="Invalid OTP"
        )

    transaction.otp_verified = "YES"
    db.commit()
    db.refresh(transaction)

    return OTPVerifyResponse(
        transaction_code=transaction.transaction_code,
        status=transaction.status,
        message="OTP verified successfully"
    )

@router.post(
    "/{transaction_code}/process",
    response_model=PaymentProcessResponse
)
def process_payment(
    transaction_code: str,
    db: Session = Depends(get_db)
):
    try:
        transaction = (
            db.query(PaymentTransaction)
            .filter(
                PaymentTransaction.transaction_code == transaction_code
            )
            .with_for_update()
            .first()
        )

        if transaction is None:
            raise HTTPException(
                status_code=404,
                detail="Transaction not found"
            )

        if transaction.status != "PENDING":
            raise HTTPException(
                status_code=400,
                detail="Transaction cannot be processed"
            )

        if transaction.otp_verified != "YES":
            raise HTTPException(
                status_code=400,
                detail="OTP has not been verified"
            )

        account = (
            db.query(Account)
            .filter(Account.id == transaction.payer_id)
            .with_for_update()
            .first()
        )

        if account is None:
            raise HTTPException(
                status_code=404,
                detail="Account not found"
            )

        tuition = (
            db.query(TuitionFee)
            .filter(TuitionFee.student_id == transaction.student_id)
            .with_for_update()
            .first()
        )

        if tuition is None:
            raise HTTPException(
                status_code=404,
                detail="Tuition fee not found"
            )

        if tuition.status == "PAID":
            raise HTTPException(
                status_code=409,
                detail="Tuition fee already paid"
            )

        if transaction.amount != tuition.amount_due:
            raise HTTPException(
                status_code=400,
                detail="Payment amount does not match tuition fee"
            )

        if account.balance < transaction.amount:
            raise HTTPException(
                status_code=400,
                detail="Insufficient balance"
            )

        account.balance -= transaction.amount
        tuition.status = "PAID"
        transaction.status = "SUCCESS"
        transaction.error_message = None

        db.commit()
        db.refresh(transaction)
        db.refresh(account)

        return PaymentProcessResponse(
            transaction_code=transaction.transaction_code,
            status=transaction.status,
            payer_id=transaction.payer_id,
            student_id=transaction.student_id,
            amount=transaction.amount,
            remaining_balance=account.balance,
            message="Payment completed successfully"
        )

    except HTTPException:
        db.rollback()
        raise

    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Payment processing failed"
        )