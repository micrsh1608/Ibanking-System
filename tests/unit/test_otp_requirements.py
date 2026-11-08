import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from services.account.database import SessionLocal as AccountSession
from services.account.models import Account, AccountEntry
from services.payment.database import SessionLocal
from services.payment.models.payment import EmailOutbox, PaymentTransaction
from services.payment.otp import code_fingerprint
from services.tuition.database import SessionLocal as TuitionSession
from services.tuition.models import TuitionInvoice


@pytest.fixture
def clock(monkeypatch):
    from services.payment import coordinator, routes
    value={'now':datetime(2030,1,1,12,0,0)}
    monkeypatch.setattr(routes,'utcnow',lambda:value['now'])
    monkeypatch.setattr(coordinator,'utcnow',lambda:value['now'])
    return value


def issue(stack,key):
    response=stack.payment.post(f'/api/v1/payments/{key}/send-otp',headers=stack.headers)
    assert response.status_code==202,response.text
    code=re.search(r'Mã OTP của bạn:\s*(\d{6})',stack.mailer.messages[-1]['body']).group(1)
    return response.json(),code


def verify(stack,key,challenge,code):
    return stack.payment.post(f'/api/v1/payments/{key}/verify-otp',headers=stack.headers,json={'challenge_id':challenge['challenge_id'],'otp':code})


def no_money_effects():
    with AccountSession() as db:
        assert db.get(Account,1).balance==Decimal('10000000.00')
        assert db.scalar(select(func.count()).select_from(AccountEntry))==0
    with TuitionSession() as db: assert all(row.status=='UNPAID' for row in db.scalars(select(TuitionInvoice)))


def test_collision_is_redrawn_and_database_independently_rejects_duplicate_fingerprint(stack,monkeypatch):
    from services.payment import routes
    first,second=stack.create()['payment_id'],stack.create()['payment_id']
    samples=iter(['111111','111111','111111','222222'])
    monkeypatch.setattr(routes,'generate_otp',lambda:next(samples))
    one,code1=issue(stack,first);two,code2=issue(stack,second)
    assert code1!=code2
    with SessionLocal() as db:
        rows=[db.get(PaymentTransaction,key) for key in (first,second)]
        assert rows[0].otp_fingerprint!=rows[1].otp_fingerprint
        assert rows[0].otp_fingerprint==code_fingerprint(code1)
        assert rows[0].otp_hash!=rows[0].otp_fingerprint and rows[0].otp_hash!=code1
    with pytest.raises(IntegrityError),SessionLocal.begin() as db:
        db.get(PaymentTransaction,second).otp_fingerprint=code_fingerprint(code1)
        db.flush()
    assert verify(stack,second,two,code1).status_code==400
    assert verify(stack,second,one,code1).status_code==400
    no_money_effects()


@pytest.mark.parametrize('elapsed,expected',[(299,200),(300,400),(301,400)])
def test_otp_is_valid_before_five_minutes_and_rejected_at_or_after_expiry(stack,clock,elapsed,expected):
    key=stack.create()['payment_id'];issued=clock['now'];challenge,code=issue(stack,key)
    assert datetime.fromisoformat(challenge['expires_at'])==issued.replace(tzinfo=timezone.utc)+timedelta(minutes=5)
    clock['now']=issued+timedelta(seconds=elapsed)
    assert verify(stack,key,challenge,code).status_code==expected
    assert stack.process(key).status_code==(200 if expected==200 else 409)
    if expected!=200:no_money_effects()


def test_verified_otp_cannot_start_processing_after_its_expiry(stack,clock):
    key=stack.create()['payment_id'];issued=clock['now'];challenge,code=issue(stack,key)
    clock['now']=issued+timedelta(seconds=299)
    assert verify(stack,key,challenge,code).status_code==200
    clock['now']=issued+timedelta(seconds=300)
    assert stack.process(key).status_code==409
    no_money_effects()


def test_consumed_code_cannot_be_verified_again_and_repeat_processing_changes_money_once(stack,clock):
    key=stack.create()['payment_id'];challenge,code=issue(stack,key)
    assert verify(stack,key,challenge,code).status_code==200
    assert verify(stack,key,challenge,code).status_code==409
    assert stack.process(key).json()['status']=='SUCCEEDED'
    assert verify(stack,key,challenge,code).status_code==409
    assert stack.process(key).json()['status']=='SUCCEEDED'
    with AccountSession() as db:
        assert db.get(Account,1).balance==Decimal('1000000.00')
        assert db.scalar(select(func.count()).select_from(AccountEntry))==1
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(EmailOutbox))==1
        assert db.get(PaymentTransaction,key).status=='SUCCEEDED'
    with TuitionSession() as db:assert all(row.status=='PAID' and row.paid_payment_id==key for row in db.scalars(select(TuitionInvoice)))


def test_resend_redraws_the_previous_code_and_invalidates_old_code_and_challenge(stack,clock,monkeypatch):
    from services.payment import routes
    key=stack.create()['payment_id'];old,old_code=issue(stack,key)
    clock['now']+=timedelta(seconds=61)
    samples=iter([old_code,old_code,'654321'])
    monkeypatch.setattr(routes,'generate_otp',lambda:next(samples))
    new,new_code=issue(stack,key)
    assert new_code!=old_code and new['challenge_id']!=old['challenge_id']
    assert verify(stack,key,old,old_code).status_code==400
    assert verify(stack,key,new,old_code).status_code==400
    assert verify(stack,key,new,new_code).status_code==200


def test_expired_code_releases_registry_slot_but_cannot_verify_original_payment(stack,clock,monkeypatch):
    from services.payment import routes
    first,second=stack.create()['payment_id'],stack.create()['payment_id']
    one,code=issue(stack,first);clock['now']+=timedelta(seconds=300)
    monkeypatch.setattr(routes,'generate_otp',lambda:code)
    two,again=issue(stack,second)
    assert again==code
    assert verify(stack,first,one,code).status_code==400
    assert verify(stack,second,two,again).status_code==200


def test_collision_retry_limit_fails_without_email_or_partial_challenge(stack,monkeypatch):
    from services.payment import routes
    first,second=stack.create()['payment_id'],stack.create()['payment_id']
    _,code=issue(stack,first)
    monkeypatch.setattr(routes,'generate_otp',lambda:code)
    response=stack.payment.post(f'/api/v1/payments/{second}/send-otp',headers=stack.headers)
    assert response.status_code==503 and len(stack.mailer.messages)==1
    with SessionLocal() as db:
        payment=db.get(PaymentTransaction,second)
        assert payment.otp_fingerprint is None and payment.otp_hash is None and payment.challenge_id is None
    no_money_effects()


def test_already_started_payment_recovers_after_otp_expiry_without_double_debit(stack,clock):
    key=stack.create()['payment_id'];issued=clock['now'];challenge,code=issue(stack,key)
    clock['now']=issued+timedelta(seconds=299)
    assert verify(stack,key,challenge,code).status_code==200
    stack.services.faults[('account','/internal/accounts/debit')]='after'
    assert stack.process(key).status_code==202
    clock['now']=issued+timedelta(minutes=6)
    assert stack.process(key).json()['status']=='SUCCEEDED'
    with AccountSession() as db:assert db.scalar(select(func.count()).select_from(AccountEntry))==1


def test_smtp_failure_clears_code_reservation_and_never_debits(stack):
    key=stack.create()['payment_id'];stack.mailer.fail=True
    assert stack.payment.post(f'/api/v1/payments/{key}/send-otp',headers=stack.headers).status_code==503
    with SessionLocal() as db:
        payment=db.get(PaymentTransaction,key)
        assert payment.otp_fingerprint is None and payment.otp_hash is None and payment.challenge_id is None
    no_money_effects()
