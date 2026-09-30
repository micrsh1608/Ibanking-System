from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.tuition import MarkPaidRequest, TuitionResponse
from app.services.tuition_service import TuitionService

router = APIRouter(prefix="/api/v1", tags=["Tuition"])


@router.get("/tuition/{mssv}", response_model=TuitionResponse)
def get_tuition(mssv: str, db: Session = Depends(get_db)):
    tuition = TuitionService.get_by_mssv(db, mssv)

    return TuitionResponse(
        mssv=tuition.student.mssv,
        full_name=tuition.student.full_name,
        email=tuition.student.email,
        amount=tuition.amount,
        status=tuition.status,
        paid_at=tuition.paid_at,
        paid_transaction_id=tuition.paid_transaction_id,
    )


@router.patch(
    "/internal/tuition/{mssv}/paid",
    response_model=TuitionResponse,
)
def mark_tuition_paid(
    mssv: str,
    request: MarkPaidRequest,
    db: Session = Depends(get_db),
):
    tuition = TuitionService.mark_paid(
        db=db,
        mssv=mssv,
        transaction_id=request.transaction_id,
    )

    return TuitionResponse(
        mssv=tuition.student.mssv,
        full_name=tuition.student.full_name,
        email=tuition.student.email,
        amount=tuition.amount,
        status=tuition.status,
        paid_at=tuition.paid_at,
        paid_transaction_id=tuition.paid_transaction_id,
    )
