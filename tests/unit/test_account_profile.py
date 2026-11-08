import re
from decimal import Decimal
from shared.time import utcnow
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from services.account.database import SessionLocal
from services.account.models import Account, User
from services.account.security import password_hasher
from tests.unit.conftest import token


@pytest.mark.parametrize('host,mode',[('mailpit','not_configured'),('smtp.example.test','smtp'),('','not_configured')])
def test_public_email_mode_does_not_expose_smtp_credentials(stack, monkeypatch, host, mode):
    monkeypatch.setenv('SMTP_HOST',host)
    monkeypatch.setenv('SMTP_PASSWORD','private-password-that-must-not-be-returned')
    response=stack.account.get('/app-config')
    assert response.status_code==200
    assert response.json()=={'email_delivery':mode,'account_email_routing':True}
    assert 'private-password-that-must-not-be-returned' not in response.text


def existing_user(stack):
    payload=dict(username='user1',password='Student_123!',full_name='Nguyễn Minh An',
        email='student@example.test',phone='0900000001',identity_number='000000000001')
    # Provision test data directly, without a public account-creation API.
    with SessionLocal.begin() as db:
        user=db.get(User,1)
        for name in ('full_name','email','phone','identity_number'):setattr(user,name,payload[name])
        user.password_hash=password_hasher.hash(payload['password'])
        user.email_verified_at=utcnow()
    response=stack.account.post('/auth/login',json={k:payload[k] for k in ('username','password')})
    assert response.status_code==200
    return payload,{'user':{'id':1}},{'Authorization':'Bearer '+response.json()['access_token']}


def profile(payload, **overrides):
    return {key:payload[key] for key in ('full_name','email','phone','identity_number')} | {'current_password':payload['password']} | overrides


def test_public_registration_is_absent_and_cannot_create_users_or_accounts(stack):
    response=stack.account.post('/auth/register',json={'username':'unwanted_signup','password':'Student_123!'})
    assert response.status_code==404
    schema=stack.account.get('/openapi.json').json()
    assert '/auth/register' not in schema['paths']
    assert not {'RegisterRequest','RegistrationResponse'} & schema['components']['schemas'].keys()
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(User))==2
        assert db.scalar(select(func.count()).select_from(Account))==2


@pytest.mark.parametrize('changes',[
    {'balance':'10000000.00'}, {'is_active':False}, {'password':'short'},
    {'email':'wrong-address'}, {'email':'a@example.test\r\nBcc: x@example.test'},
    {'username':'bad user'}, {'full_name':'  '}, {'phone':'-------'}, {'phone':'1234567890123456'},
])
def test_profile_rejects_invalid_contact_and_financial_input(stack, changes):
    payload,_,headers=existing_user(stack)
    response=stack.account.put('/users/me',headers=headers,json=profile(payload,**changes))
    assert response.status_code==422
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(User))==2
        assert db.scalar(select(func.count()).select_from(Account))==2


def test_profile_requires_password_and_rejects_changes_to_other_identity_or_balance(stack):
    payload, result, headers=existing_user(stack)
    assert stack.account.put('/users/me',json=profile(payload)).status_code==401
    assert stack.account.put('/users/me',headers=headers,json=profile(payload,current_password='wrong-password',email='new@example.test')).status_code==403
    for changes in ({'id':1},{'balance':'1000000.00'},{'username':'user1'},{'account_number':'123'}):
        assert stack.account.put('/users/me',headers=headers,json=profile(payload,**changes)).status_code==422
    unchanged=stack.account.get('/users/me',headers=headers).json()
    assert unchanged['id']==result['user']['id'] and unchanged['email']==payload['email']
    assert stack.account.get('/accounts/me',headers=headers).json()['balance']=='10000000.00'


def test_profile_update_persists_and_new_payment_uses_new_email_without_rewriting_old_snapshot(stack):
    payload, user, headers=existing_user(stack)
    with SessionLocal.begin() as db:
        account = db.scalar(select(Account).where(Account.user_id == user['user']['id']))
        account.balance = Decimal('10000000.00')  # Test funding, never a public self-credit API.
    original=stack.payment.post('/api/v1/payments',headers=headers | {'Idempotency-Key':str(uuid4())},
        json={'mssv':'SV2026001','selection_mode':'ALL_UNPAID','terms_accepted':True})
    assert original.status_code==201
    assert stack.payment.post('/api/v1/payments/'+original.json()['payment_id']+'/send-otp',headers=headers).status_code==202
    updated=stack.account.put('/users/me',headers=headers,json=profile(payload,email='new-address@example.test',full_name='Nguyễn Minh Bình'))
    assert updated.status_code==202 and updated.json()['email']==payload['email']
    code=re.search(r'Mã xác minh email của bạn:\s*(\d{6})',stack.mailer.messages[-1]['body']).group(1)
    assert stack.account.post('/users/me/email-verification/confirm',headers=headers,json={'challenge_id':updated.json()['email_verification']['challenge_id'],'code':code}).status_code==200
    assert stack.account.get('/users/me',headers=headers).json()['email']=='new-address@example.test'
    newer=stack.payment.post('/api/v1/payments',headers=headers | {'Idempotency-Key':str(uuid4())},
        json={'mssv':'SV2026001','selection_mode':'ALL_UNPAID','terms_accepted':True})
    assert newer.status_code==201
    assert stack.payment.post('/api/v1/payments/'+original.json()['payment_id']+'/send-otp',headers=headers).status_code==409
    assert stack.payment.post('/api/v1/payments/'+newer.json()['payment_id']+'/send-otp',headers=headers).status_code==202
    financial=[mail['recipient'] for mail in stack.mailer.messages if 'Mã xác thực' in mail['subject']]
    assert financial==[payload['email'],'new-address@example.test']
    other={'Authorization':'Bearer '+token(2)}
    assert stack.account.get('/users/me',headers=other).json()['email']=='user2@example.test'
