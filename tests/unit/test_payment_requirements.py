from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from services.account.database import SessionLocal as AccountSession
from services.account.models import Account, AccountEntry, User
from services.payment.database import SessionLocal as PaymentSession
from services.payment.models.payment import PaymentTransaction
from services.tuition.database import SessionLocal as TuitionSession
from services.tuition.models import TuitionInvoice


def create(stack, **changes):
    return stack.payment.post('/api/v1/payments', headers=stack.headers | {'Idempotency-Key':str(uuid4())},
        json={'mssv':'SV2026001','selection_mode':'ALL_UNPAID','terms_accepted':True} | changes)


def no_effects():
    with PaymentSession() as db:
        assert db.scalar(select(func.count()).select_from(PaymentTransaction)) == 0
    with AccountSession() as db:
        assert db.scalar(select(func.count()).select_from(AccountEntry)) == 0


@pytest.mark.parametrize('changes',[{'terms_accepted':False},{'terms_accepted':'true'},{'terms_accepted':1},
    {'selection_mode':'SELECTED','invoice_ids':[1]}, {'invoice_ids':[1]}, {'amount':'100000.00'}, {'payer_user_id':2}])
def test_full_debt_requires_consent_and_rejects_partial_or_client_controlled_money(stack, changes):
    assert create(stack,**changes).status_code == 422
    no_effects()


def test_missing_consent_cannot_create_payment(stack):
    response=stack.payment.post('/api/v1/payments',headers=stack.headers | {'Idempotency-Key':str(uuid4())},json={'mssv':'SV2026001'})
    assert response.status_code == 422
    no_effects()


@pytest.mark.parametrize('field,value',[('full_name',''),('email','bad-address'),('phone',None),('phone','bad-phone'),('phone','-------'),('phone','1234567890123456')])
def test_payer_contact_must_be_complete_from_authenticated_profile(stack,field,value):
    with AccountSession.begin() as db:
        setattr(db.get(User,1),field,value)
    assert create(stack).status_code == 409
    no_effects()


@pytest.mark.parametrize('condition',['low_balance','locked','paid','reserved','missing_student'])
def test_ineligible_lookup_cannot_create_payment_or_ledger(stack,condition):
    if condition in {'low_balance','locked'}:
        with AccountSession.begin() as db:
            account=db.get(Account,1)
            if condition=='low_balance': account.balance=Decimal('8999999.99')
            else: account.status='LOCKED'
    if condition in {'paid','reserved'}:
        with TuitionSession.begin() as db:
            for row in db.scalars(select(TuitionInvoice)):
                row.status='PAID' if condition=='paid' else ('RESERVED' if row.id==1 else 'UNPAID')
    response=create(stack,**({'mssv':'NOT_FOUND'} if condition=='missing_student' else {}))
    assert response.status_code == (404 if condition=='missing_student' else 409)
    no_effects()


def test_balance_equal_total_is_allowed_and_records_consent(stack):
    with AccountSession.begin() as db: db.get(Account,1).balance=Decimal('9000000.00')
    payment=create(stack)
    assert payment.status_code==201
    result=payment.json()
    assert result['terms_version']=='2026-11-03' and result['terms_accepted_at']
    assert [item['invoice_id'] for item in result['items']]==[1,2,3]
    stack.verify(result['payment_id'])
    assert stack.process(result['payment_id']).json()['status']=='SUCCEEDED'
    with AccountSession() as db: assert db.get(Account,1).balance==0


def test_new_invoice_after_snapshot_requires_full_reconfirmation_and_no_debit(stack):
    payment=stack.create()
    with TuitionSession.begin() as db:
        db.add(TuitionInvoice(student_id=1,semester='NEW-HK4',amount_due=Decimal('100000.00')))
    stack.verify(payment['payment_id'])
    result=stack.process(payment['payment_id'])
    assert result.status_code==409 and result.json()['status']=='FAILED'
    with AccountSession() as db:
        assert db.get(Account,1).balance==Decimal('10000000.00')
        assert db.scalar(select(func.count()).select_from(AccountEntry))==0
    with TuitionSession() as db: assert all(row.status=='UNPAID' for row in db.scalars(select(TuitionInvoice)))


def test_legacy_unstarted_selected_draft_cannot_start_but_history_is_preserved(stack):
    key=stack.create()['payment_id']
    with PaymentSession.begin() as db:
        row=db.get(PaymentTransaction,key); row.selection_mode='SELECTED'; row.terms_accepted_at=None; row.terms_version=None
    assert stack.payment.post(f'/api/v1/payments/{key}/send-otp',headers=stack.headers).status_code==409
    result=stack.process(key)
    assert result.status_code==409 and result.json()['status']=='FAILED'
    assert stack.payment.get(f'/api/v1/payments/{key}',headers=stack.headers).status_code==200
    with AccountSession() as db: assert db.scalar(select(func.count()).select_from(AccountEntry))==0
