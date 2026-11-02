import logging
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from services.account.database import SessionLocal
from services.account.internal_security import require_internal_key
from services.account.models import Account, AccountEntry, AccountCancellation
from shared.locking import transaction_lock
from services.account.schemas import (
    DebitRequest,
    RefundRequest,
    OperationResponse,
)


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/internal",
    tags=["Internal Accounts"],
    dependencies=[Depends(require_internal_key)],
)

MAX_BALANCE = Decimal("9999999999999999.99")


def get_transaction():
    try:
        with SessionLocal.begin() as db:
            yield db

    except DBAPIError:
        logger.exception("Lỗi database khi xử lý giao dịch")

        raise HTTPException(
            status_code=503,
            detail=(
                "Chưa xác nhận được kết quả. "
                "Tra cứu lại theo payment_id; "
                "nếu thử lại, giữ nguyên payment_id và dữ liệu."
            ),
        ) from None


def load_entries(db: Session, payment_id: str):
    transaction_lock(db, 'account:' + payment_id)
    statement = (
        select(AccountEntry)
        .where(AccountEntry.payment_id == payment_id)
    )

    entries = db.scalars(statement).all()

    return {
        entry.entry_type: entry
        for entry in entries
    }


def load_account(db: Session, account_id: int):
    statement = (
        select(Account)
        .where(Account.id == account_id)
        .with_hint(
            Account,
            "WITH (UPDLOCK, HOLDLOCK)",
            dialect_name="mssql",
        )
    )

    account = db.scalar(statement)

    if account is None:
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy tài khoản",
        )

    return account


def operation_result(debit: AccountEntry, refunded: bool):
    return OperationResponse(
        payment_id=debit.payment_id,
        account_id=debit.account_id,
        amount=debit.amount,
        status="REFUNDED" if refunded else "DEBITED",
    )


@router.post(
    "/accounts/debit",
    response_model=OperationResponse,
)
def debit_account(
    data: DebitRequest,
    db: Session = Depends(get_transaction, scope="function"),
):
    payment_id = str(data.payment_id)

    # Luôn khóa theo mã giao dịch trước, rồi đến tài khoản.
    entries = load_entries(db, payment_id)
    cancelled = db.get(AccountCancellation, payment_id)
    if cancelled is not None:
        if (cancelled.account_id != data.account_id or cancelled.payer_user_id != data.payer_user_id
                or cancelled.amount != data.amount):
            raise HTTPException(409, 'payment_id đã dùng với dữ liệu khác')
        return OperationResponse(payment_id=payment_id, account_id=data.account_id, amount=data.amount,
            status='REFUNDED' if 'REFUND' in entries else 'CANCELLED')
    previous_debit = entries.get("DEBIT")

    if previous_debit is not None:
        if (
            previous_debit.account_id != data.account_id
            or previous_debit.amount != data.amount
        ):
            raise HTTPException(
                status_code=409,
                detail="payment_id đã được dùng với dữ liệu khác",
            )

        account = load_account(db, previous_debit.account_id)

        if account.user_id != data.payer_user_id:
            raise HTTPException(
                status_code=403,
                detail="Tài khoản không thuộc người thanh toán",
            )

        # Nếu đã hoàn tiền, trả REFUNDED; không trừ lần nữa.
        return operation_result(
            previous_debit,
            refunded="REFUND" in entries,
        )

    account = load_account(db, data.account_id)

    if account.user_id != data.payer_user_id:
        raise HTTPException(
            status_code=403,
            detail="Tài khoản không thuộc người thanh toán",
        )

    if account.status != "ACTIVE":
        raise HTTPException(
            status_code=409,
            detail="Tài khoản đang bị khóa",
        )

    if account.balance < data.amount:
        raise HTTPException(
            status_code=409,
            detail="Số dư không đủ",
        )

    account.balance -= data.amount

    debit = AccountEntry(
        payment_id=payment_id,
        account_id=account.id,
        entry_type="DEBIT",
        amount=data.amount,
    )

    db.add(debit)
    db.flush()

    return operation_result(debit, refunded=False)


@router.post(
    "/accounts/refund",
    response_model=OperationResponse,
)
def refund_account(
    data: RefundRequest,
    db: Session = Depends(get_transaction, scope="function"),
):
    payment_id = str(data.payment_id)

    entries = load_entries(db, payment_id)
    debit = entries.get("DEBIT")

    if debit is None:
        raise HTTPException(
            status_code=404,
            detail="Chưa tìm thấy khoản trừ tiền để hoàn",
        )

    if "REFUND" in entries:
        return operation_result(debit, refunded=True)

    account = load_account(db, debit.account_id)

    if account.balance + debit.amount > MAX_BALANCE:
        raise HTTPException(
            status_code=409,
            detail="Số dư sau hoàn tiền vượt giới hạn lưu trữ",
        )

    # Hoàn đúng số tiền của giao dịch gốc.
    # Vẫn cho nhận lại tiền khi tài khoản đang LOCKED.
    account.balance += debit.amount

    refund = AccountEntry(
        payment_id=payment_id,
        account_id=debit.account_id,
        entry_type="REFUND",
        amount=debit.amount,
    )

    db.add(refund)
    db.flush()

    return operation_result(debit, refunded=True)


@router.get(
    "/account-operations/{payment_id}",
    response_model=OperationResponse,
)
def get_operation(
    payment_id: UUID,
    db: Session = Depends(get_transaction, scope="function"),
):
    entries = load_entries(db, str(payment_id))
    debit = entries.get("DEBIT")

    if debit is None:
        cancelled = db.get(AccountCancellation, str(payment_id))
        if cancelled is not None:
            return OperationResponse(payment_id=str(payment_id), account_id=cancelled.account_id,
                amount=cancelled.amount, status='CANCELLED')
        raise HTTPException(
            status_code=404,
            detail="Chưa ghi nhận khoản trừ tiền",
        )

    return operation_result(
        debit,
        refunded="REFUND" in entries,
    )


@router.post('/accounts/cancel', response_model=OperationResponse)
def cancel_account_operation(data: DebitRequest, db: Session = Depends(get_transaction, scope='function')):
    payment_id = str(data.payment_id)
    entries = load_entries(db, payment_id)
    cancelled = db.get(AccountCancellation, payment_id)
    if cancelled is not None:
        if (cancelled.account_id != data.account_id or cancelled.payer_user_id != data.payer_user_id
                or cancelled.amount != data.amount):
            raise HTTPException(409, 'payment_id đã dùng với dữ liệu khác')
        return OperationResponse(payment_id=payment_id, account_id=data.account_id, amount=data.amount,
            status='REFUNDED' if 'REFUND' in entries else 'CANCELLED')
    debit = entries.get('DEBIT')
    if debit is not None and (debit.account_id != data.account_id or debit.amount != data.amount):
        raise HTTPException(409, 'Khoản trừ tiền không khớp; không được hoàn nhầm giao dịch')
    account = load_account(db, data.account_id)
    if account.user_id != data.payer_user_id:
        raise HTTPException(403, 'Tài khoản không thuộc người thanh toán')
    if debit is not None and 'REFUND' not in entries:
        if account.balance + debit.amount > MAX_BALANCE:
            raise HTTPException(409, 'Số dư sau hoàn vượt giới hạn')
        account.balance += debit.amount
        db.add(AccountEntry(payment_id=payment_id, account_id=account.id, entry_type='REFUND', amount=debit.amount))
    db.add(AccountCancellation(payment_id=payment_id, account_id=account.id,
        payer_user_id=data.payer_user_id, amount=data.amount))
    db.flush()
    return OperationResponse(payment_id=payment_id, account_id=account.id, amount=data.amount,
        status='REFUNDED' if debit is not None else 'CANCELLED')
