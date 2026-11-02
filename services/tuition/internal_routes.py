"""Atomic, idempotent invoice groups with durable cancellation tombstones."""
import hashlib
import json
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from services.tuition.database import SessionLocal
from services.tuition.models import Reservation, ReservationItem, Student, TuitionInvoice
from services.tuition.routes import get_tuition
from services.tuition.schemas import ReserveRequest, ReservationView, TuitionView
from shared.auth import require_internal_key
from shared.locking import transaction_lock
from shared.time import utcnow

router = APIRouter(prefix='/internal/tuition', tags=['Internal Tuition'], dependencies=[Depends(require_internal_key)])


def transaction():
    try:
        with SessionLocal.begin() as db:
            yield db
    except DBAPIError:
        raise HTTPException(503, 'Kết quả chưa rõ; thử lại cùng payment_id') from None


def view(row):
    return ReservationView(payment_id=row.payment_id, status=row.status, mssv=row.mssv,
        total_amount=row.total_amount, invoice_ids=[item.invoice_id for item in row.items])


def load(db, payment_id):
    transaction_lock(db, 'tuition:' + payment_id)
    return db.get(Reservation, payment_id)


def invoices_locked(db, ids):
    # Acquire in a stable order, including when groups overlap.
    rows = []
    for invoice_id in sorted(ids):
        row = db.scalar(select(TuitionInvoice).where(TuitionInvoice.id == invoice_id)
            .with_hint(TuitionInvoice, 'WITH (UPDLOCK, HOLDLOCK)', dialect_name='mssql'))
        if row is None:
            raise HTTPException(404, 'Không tìm thấy hóa đơn')
        rows.append(row)
    return rows


@router.get('/invoices', response_model=TuitionView)
def snapshot(mssv: str = Query(min_length=1, max_length=24), db=Depends(transaction, scope='function')):
    return get_tuition(mssv, _user_id=0, db=db)


@router.post('/reservations', response_model=ReservationView)
def reserve(data: ReserveRequest, db=Depends(transaction, scope='function')):
    payment_id = str(data.payment_id)
    payload = {'mssv': data.mssv, 'items': sorted((item.invoice_id, item.version) for item in data.items),
        'total': format(data.expected_total, '.2f')}
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    previous = load(db, payment_id)
    if previous is not None:
        if previous.status == 'RELEASED':
            raise HTTPException(409, 'Giao dịch đã bị hủy; không thể giữ hóa đơn lại')
        if previous.request_hash != fingerprint:
            raise HTTPException(409, 'payment_id đã dùng với dữ liệu khác')
        return view(previous)
    student = db.scalar(select(Student).where(Student.mssv == data.mssv))
    if student is None:
        raise HTTPException(404, 'Không tìm thấy MSSV')
    versions = {item.invoice_id: item.version for item in data.items}
    rows = invoices_locked(db, versions)
    for row in rows:
        if row.student_id != student.id:
            raise HTTPException(409, 'Hóa đơn không thuộc MSSV đã chọn')
        if row.status != 'UNPAID' or row.version != versions[row.id]:
            raise HTTPException(409, 'Hóa đơn đã thay đổi, đang xử lý hoặc đã thanh toán')
    total = sum((row.amount_due for row in rows), Decimal('0.00'))
    if total != data.expected_total:
        raise HTTPException(409, 'Tổng tiền đã thay đổi; xác nhận lại hóa đơn')
    reservation = Reservation(payment_id=payment_id, request_hash=fingerprint,
        mssv=data.mssv, total_amount=total, status='RESERVED')
    db.add(reservation)
    db.flush()
    for row in rows:
        row.status = 'RESERVED'
        row.reserved_payment_id = payment_id
        row.version += 1
        db.add(ReservationItem(payment_id=payment_id, invoice_id=row.id, amount=row.amount_due))
    db.flush()
    return view(reservation)


@router.get('/reservations/{payment_id}', response_model=ReservationView)
def status(payment_id: UUID, db=Depends(transaction, scope='function')):
    row = load(db, str(payment_id))
    if row is None:
        raise HTTPException(404, 'Chưa ghi nhận nhóm hóa đơn')
    return view(row)


@router.post('/reservations/{payment_id}/finalize', response_model=ReservationView)
def finalize(payment_id: UUID, db=Depends(transaction, scope='function')):
    key = str(payment_id)
    row = load(db, key)
    if row is None:
        raise HTTPException(404, 'Chưa giữ hóa đơn')
    if row.status == 'PAID':
        return view(row)
    if row.status == 'RELEASED':
        raise HTTPException(409, 'Nhóm hóa đơn đã hủy')
    invoices = invoices_locked(db, [item.invoice_id for item in row.items])
    for invoice in invoices:
        if invoice.status != 'RESERVED' or invoice.reserved_payment_id != key:
            raise HTTPException(409, 'Trạng thái giữ hóa đơn không khớp')
    for invoice in invoices:
        invoice.status = 'PAID'
        invoice.paid_payment_id = key
        invoice.paid_at = utcnow()
        invoice.reserved_until = None
        invoice.version += 1
    row.status = 'PAID'
    return view(row)


@router.post('/reservations/{payment_id}/release', response_model=ReservationView)
def release(payment_id: UUID, db=Depends(transaction, scope='function')):
    key = str(payment_id)
    row = load(db, key)
    if row is None:
        # Close the race even when the original reserve request has not arrived yet.
        row = Reservation(payment_id=key, status='RELEASED', total_amount=Decimal('0.00'))
        db.add(row)
        db.flush()
    elif row.status == 'PAID':
        raise HTTPException(409, 'Đã thanh toán; không thể nhả hóa đơn')
    elif row.status != 'RELEASED':
        invoices = invoices_locked(db, [item.invoice_id for item in row.items])
        for invoice in invoices:
            if invoice.status != 'RESERVED' or invoice.reserved_payment_id != key:
                raise HTTPException(409, 'Trạng thái hóa đơn không khớp')
        for invoice in invoices:
            invoice.status = 'UNPAID'
            invoice.reserved_payment_id = None
            invoice.reserved_until = None
            invoice.version += 1
        row.status = 'RELEASED'
    return view(row)
