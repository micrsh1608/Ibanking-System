from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from services.tuition.auth import require_user_id
from services.tuition.database import get_db
from services.tuition.models import Student
from services.tuition.schemas import InvoiceView, TuitionView

router = APIRouter(prefix='/api/v1/tuition', tags=['Tuition'])


@router.get('/{mssv}', response_model=TuitionView)
def get_tuition(
    mssv: str,
    _user_id: int = Depends(require_user_id),
    db: Session = Depends(get_db),
):
    if not (1 <= len(mssv) <= 24):
        raise HTTPException(status_code=422, detail='MSSV không hợp lệ')

    student = db.scalar(
        select(Student)
        .options(selectinload(Student.invoices))
        .where(Student.mssv == mssv)
    )
    if student is None:
        raise HTTPException(status_code=404, detail='Không tìm thấy MSSV')

    invoices = sorted(student.invoices, key=lambda r: r.id)
    total = sum((row.amount_due for row in invoices if row.status == 'UNPAID'), Decimal('0.00'))
    return TuitionView(
        mssv=student.mssv,
        full_name=student.full_name,
        total_unpaid=total,
        invoices=[InvoiceView.model_validate(row) for row in invoices],
    )
