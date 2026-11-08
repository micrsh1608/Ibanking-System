import re
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from services.account.database import SessionLocal
from services.account.models import User, AccountEntry
from services.account.security import password_hasher
from services.account import email_verification as proof, routes
from tests.unit.conftest import token

PASSWORD='EmailProof_123!'


@pytest.fixture
def user(stack, monkeypatch):
    clock={'now':datetime(2030,1,1,12,0,0)}
    monkeypatch.setattr(proof,'utcnow',lambda:clock['now'])
    monkeypatch.setattr(routes,'utcnow',lambda:clock['now'])
    with SessionLocal.begin() as db:
        row=db.get(User,1);row.password_hash=password_hasher.hash(PASSWORD);row.email_verified_at=None
    return clock


def start(stack,email='candidate@example.test',**changes):
    data={'full_name':'New Owner Name','email':email,'phone':'0900000002','identity_number':'000000000002','current_password':PASSWORD}|changes
    return stack.account.put('/users/me',headers=stack.headers,json=data)


def code(stack):
    return re.search(r'Mã xác minh email của bạn:\s*(\d{6})',stack.mailer.messages[-1]['body']).group(1)


def confirm(stack,challenge,value,headers=None):
    return stack.account.post('/users/me/email-verification/confirm',headers=headers or stack.headers,json={'challenge_id':challenge,'code':value})


def no_debit():
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(AccountEntry))==0


def test_smtp_acceptance_does_not_save_or_verify_a_nonexistent_candidate_and_cannot_pay(stack,user,capsys):
    response=start(stack,'nonexistent@example.test');assert response.status_code==202
    result=response.json();actual=code(stack)
    assert result['email']=='user1@example.test' and result['email_verified'] is False
    assert result['full_name']=='User 1' and result['pending_email']=='nonexistent@example.test'
    assert actual not in response.text and actual not in capsys.readouterr().out
    assert not {'email_code_hash','email_pending_profile','email_code_attempts'} & result.keys()
    assert stack.payment.post('/api/v1/payments',headers=stack.headers|{'Idempotency-Key':str(uuid4())},json={'mssv':'SV2026001','terms_accepted':True}).status_code==409
    with SessionLocal() as db:assert db.get(User,1).email_verified_at is None
    no_debit()


def test_correct_inbox_proof_atomically_saves_the_profile_and_consumes_the_challenge(stack,user):
    challenge=start(stack).json()['email_verification']['challenge_id'];value=code(stack)
    assert confirm(stack,challenge,value,{'Authorization':'Bearer '+token(2)}).status_code==409
    result=confirm(stack,challenge,value)
    assert result.status_code==200
    assert result.json()['email']=='candidate@example.test' and result.json()['email_verified'] is True
    assert result.json()['full_name']=='New Owner Name' and result.json()['phone']=='0900000002'
    assert result.json()['pending_email'] is None and result.json()['email_verification'] is None
    assert confirm(stack,challenge,value).status_code==409
    with SessionLocal() as db:
        row=db.get(User,1);assert row.email_code_hash is None and row.email_pending_profile is None
    assert stack.create()['payer_email']=='candidate@example.test'


@pytest.mark.parametrize('elapsed,expected',[(299,200),(300,400),(301,400)])
def test_email_proof_expires_at_exactly_five_minutes(stack,user,elapsed,expected):
    issued=start(stack).json()['email_verification']['challenge_id'];value=code(stack)
    user['now']+=timedelta(seconds=elapsed)
    assert confirm(stack,issued,value).status_code==expected
    if expected!=200:assert stack.account.get('/users/me',headers=stack.headers).json()['email_verified'] is False
    no_debit()


def test_wrong_code_attempts_persist_and_sixth_attempt_is_blocked_even_if_correct(stack,user):
    challenge=start(stack).json()['email_verification']['challenge_id'];value=code(stack)
    wrong='000000' if value!='000000' else '111111'
    for _ in range(5):assert confirm(stack,challenge,wrong).status_code==400
    assert confirm(stack,challenge,value).status_code==429
    assert stack.account.get('/users/me',headers=stack.headers).json()['email']=='user1@example.test'
    no_debit()


def test_resend_cooldown_replaces_both_code_and_challenge(stack,user,monkeypatch):
    first=start(stack).json()['email_verification']['challenge_id'];old=code(stack)
    assert stack.account.post('/users/me/email-verification/resend',headers=stack.headers,json={'current_password':PASSWORD}).status_code==429
    user['now']+=timedelta(seconds=60)
    values=iter([old,old,'222222' if old!='222222' else '333333'])
    monkeypatch.setattr(proof,'generate_code',lambda:next(values))
    result=stack.account.post('/users/me/email-verification/resend',headers=stack.headers,json={'current_password':PASSWORD})
    assert result.status_code==202
    second=result.json()['email_verification']['challenge_id'];new=code(stack)
    assert second!=first and new!=old
    assert confirm(stack,first,old).status_code==409
    assert confirm(stack,second,old).status_code==400
    assert confirm(stack,second,new).status_code==200


def test_smtp_rejection_preserves_old_profile_and_clears_pending_proof(stack,user):
    stack.mailer.fail=True
    assert start(stack).status_code==503
    result=stack.account.get('/users/me',headers=stack.headers).json()
    assert result['email']=='user1@example.test' and result['full_name']=='User 1'
    assert result['email_verified'] is False and result['pending_email'] is None
    with SessionLocal() as db:assert db.get(User,1).email_code_hash is None
    no_debit()


def test_cancel_preserves_current_email_and_invalidates_code(stack,user):
    challenge=start(stack).json()['email_verification']['challenge_id'];value=code(stack)
    result=stack.account.delete('/users/me/email-verification',headers=stack.headers)
    assert result.status_code==200 and result.json()['email']=='user1@example.test'
    assert result.json()['email_verified'] is False and result.json()['pending_email'] is None
    assert confirm(stack,challenge,value).status_code==409


@pytest.mark.parametrize('extra',[{'email_verified':True},{'email_verified_at':'2030-01-01'},{'email_code_hash':'fake'},{'pending_email':'fake@example.test'}])
def test_public_profile_cannot_forge_verification_state(stack,user,extra):
    assert start(stack,**extra).status_code==422


def test_an_existing_verified_address_remains_active_while_a_different_address_waits_for_proof(stack,user):
    with SessionLocal.begin() as db:db.get(User,1).email_verified_at=user['now']
    result=start(stack).json()
    assert result['email']=='user1@example.test' and result['email_verified'] is True
    assert result['pending_email']=='candidate@example.test'
    assert stack.create()['payer_email']=='user1@example.test'


def test_old_transaction_challenge_cannot_bypass_an_unverified_email(stack,user):
    with SessionLocal.begin() as db:db.get(User,1).email_verified_at=user['now']
    payment=stack.create();stack.verify(payment['payment_id'])
    with SessionLocal.begin() as db:db.get(User,1).email_verified_at=None
    assert stack.payment.post('/api/v1/payments/'+payment['payment_id']+'/send-otp',headers=stack.headers).status_code==409
    assert stack.process(payment['payment_id']).status_code==409
    no_debit()


def test_recovery_of_already_started_money_effects_is_not_stranded_by_email_status(stack,user):
    with SessionLocal.begin() as db:db.get(User,1).email_verified_at=user['now']
    payment=stack.create();stack.verify(payment['payment_id'])
    stack.services.faults[('account','/internal/accounts/debit')]='after'
    assert stack.process(payment['payment_id']).status_code==202
    with SessionLocal.begin() as db:db.get(User,1).email_verified_at=None
    assert stack.process(payment['payment_id']).json()['status']=='SUCCEEDED'
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(AccountEntry))==1
