"""SMTP-only recipient routing, with fake transports and isolated SQLite data."""
import hashlib
import hmac
import os
import re
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from shared import mailer
from shared.time import utcnow
from services.account import email_verification as proof
from services.account.database import Base, SessionLocal
from services.account.models import User
from services.account.security import password_hasher
from tests.unit.conftest import token


PASSWORD = 'RoutingDemo_123!'


@pytest.fixture
def transport(monkeypatch):
    calls = []

    class SMTP:
        def __init__(self, **options):
            calls.append({'event': 'connect', **options})

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def starttls(self, **options):
            calls.append({'event': 'starttls'})

        def login(self, username, password):
            calls.append({'event': 'login', 'username': username})

        def send_message(self, message, **options):
            calls.append({'event': 'send', 'from': str(message['From']),
                'to': str(message['To']), 'recipients': options['to_addrs'],
                'subject': str(message['Subject']), 'body': message.get_content()})
            return {}

    monkeypatch.setattr(mailer.smtplib, 'SMTP', SMTP)
    monkeypatch.setattr(mailer.smtplib, 'SMTP_SSL', SMTP)
    for key, value in {'SMTP_HOST': 'smtp.example.test', 'SMTP_PORT': '587',
            'SMTP_USERNAME': 'owner@example.test', 'SMTP_PASSWORD': 'synthetic-password',
            'SMTP_FROM': 'iBanking <sender@example.test>',
            'SMTP_STARTTLS': 'true', 'SMTP_SSL': 'false'}.items():
        monkeypatch.setenv(key, value)
    return calls


def send(channel='configured'):
    mailer.Mailer().send(recipient='receiver@example.test', subject='Routing test',
                        body='Synthetic message', message_id='routing-test', channel=channel)


@pytest.mark.parametrize('channel,host,expected', [
    ('configured', 'smtp.example.test', 'smtp'),
    ('smtp', 'smtp.example.test', 'smtp'),
    ('configured', 'mailpit', 'not_configured'),
    ('smtp', 'mailpit', 'not_configured'),
    ('configured', '', 'not_configured'),
    ('smtp', '', 'not_configured'),
    ('mailpit', 'smtp.example.test', 'not_configured'),
    ('invalid', 'smtp.example.test', 'not_configured'),
])
def test_route_resolution_is_explicit_and_does_not_connect(monkeypatch, channel, host, expected):
    monkeypatch.setenv('SMTP_HOST', host)
    assert mailer.resolve_email_channel(channel) == expected


@pytest.mark.parametrize('channel', ['configured', 'smtp'])
def test_smtp_uses_the_requested_recipient_in_header_and_envelope(transport, channel):
    send(channel)
    messages = [row for row in transport if row['event'] == 'send']
    assert len(messages) == 1
    assert messages[0]['from'] == 'iBanking <sender@example.test>'
    assert messages[0]['to'] == 'receiver@example.test'
    assert messages[0]['recipients'] == ['receiver@example.test']
    assert any(row == {'event': 'login', 'username': 'owner@example.test'} for row in transport)


@pytest.mark.parametrize('channel', ['configured', 'smtp'])
@pytest.mark.parametrize('host', ['mailpit', ''])
def test_unavailable_real_smtp_is_rejected_before_connect(transport, monkeypatch, host, channel):
    monkeypatch.setenv('SMTP_HOST', host)
    with pytest.raises(mailer.MailError):
        send(channel)
    assert transport == []


def test_legacy_mailpit_route_is_rejected_even_when_smtp_is_available(transport):
    with pytest.raises(mailer.MailError):
        send('mailpit')
    assert transport == []
    with pytest.raises(ValueError):
        mailer.transport_settings('mailpit')


def test_smtp_failure_does_not_redirect_to_another_transport(transport, monkeypatch):
    calls = []

    def fail(**options):
        calls.append(options['host'])
        raise OSError('Synthetic SMTP failure')

    monkeypatch.setattr(mailer.smtplib, 'SMTP', fail)
    with pytest.raises(mailer.MailError):
        send('smtp')
    assert calls == ['smtp.example.test']


@pytest.fixture
def routing_user(stack, monkeypatch):
    monkeypatch.setenv('SMTP_HOST', 'smtp.example.test')
    with SessionLocal.begin() as db:
        user = db.get(User, 1)
        user.password_hash = password_hasher.hash(PASSWORD)
        user.email_channel = 'smtp'
        user.email_verified_at = None


def start_proof(stack, **extra):
    return stack.account.put('/users/me', headers=stack.headers, json={
        'full_name': 'Routing Profile', 'email': 'candidate@example.test',
        'phone': '0900000002', 'identity_number': '000000000002',
        'current_password': PASSWORD, **extra})


def proof_code(stack):
    return re.search(r':\s*(\d{6})', stack.mailer.messages[-1]['body']).group(1)


def confirm_proof(stack, challenge, code):
    return stack.account.post('/users/me/email-verification/confirm', headers=stack.headers,
        json={'challenge_id': challenge, 'code': code})


def test_profile_and_public_config_report_smtp_without_mailpit_link(stack, routing_user):
    result = stack.account.get('/users/me', headers=stack.headers)
    assert result.status_code == 200
    assert result.json()['email_delivery'] == 'smtp'
    assert 'email_channel' not in result.json()
    config = stack.account.get('/app-config').json()
    assert config['email_delivery'] == 'smtp'
    assert 'mailpit_url' not in config
    assert 'mailpit' not in str(config).lower()


@pytest.mark.parametrize('extra', [
    {'email_channel': 'smtp'}, {'email_channel': 'mailpit'},
    {'email_delivery': 'smtp'}, {'email_pending_channel': 'smtp'},
])
def test_public_profile_cannot_select_a_mail_delivery_route(stack, routing_user, extra):
    assert start_proof(stack, **extra).status_code == 422
    with SessionLocal() as db:
        assert db.get(User, 1).email_channel == 'smtp'


def test_email_proof_is_delivered_to_candidate_and_bound_to_smtp(stack, routing_user):
    pending = start_proof(stack)
    assert pending.status_code == 202
    assert stack.mailer.messages[-1]['channel'] == 'smtp'
    assert stack.mailer.messages[-1]['recipient'] == 'candidate@example.test'
    value = proof_code(stack)
    with SessionLocal() as db:
        user = db.get(User, 1)
        assert user.email_pending_channel == 'smtp'
        assert user.email_code_hash == proof.hash_code(user, value)
        user.email_pending_channel = 'configured'
        assert user.email_code_hash != proof.hash_code(user, value)
    confirmed = confirm_proof(stack, pending.json()['email_verification']['challenge_id'], value)
    assert confirmed.status_code == 200
    assert confirmed.json()['email_delivery'] == 'smtp'
    with SessionLocal() as db:
        assert db.get(User, 1).email_pending_channel is None


def test_unavailable_route_invalidates_pending_proof_without_saving_profile(stack, routing_user):
    pending = start_proof(stack)
    value = proof_code(stack)
    with SessionLocal.begin() as db:
        db.get(User, 1).email_channel = 'mailpit'
    result = confirm_proof(stack, pending.json()['email_verification']['challenge_id'], value)
    assert result.status_code == 409
    with SessionLocal() as db:
        user = db.get(User, 1)
        assert user.email == 'user1@example.test' and user.full_name == 'User 1'
        assert user.email_code_hash is None and user.email_pending_channel is None
        assert user.email_verified_at is None


def test_name_phone_update_with_same_verified_email_requires_proof_before_commit(stack, routing_user):
    with SessionLocal.begin() as db:
        db.get(User, 1).email_verified_at = utcnow()
    pending = start_proof(stack, email='user1@example.test')
    assert pending.status_code == 202
    assert pending.json()['full_name'] == 'User 1'
    assert pending.json()['phone'] == '0900000001'
    assert stack.mailer.messages[-1]['recipient'] == 'user1@example.test'
    confirmed = confirm_proof(stack, pending.json()['email_verification']['challenge_id'], proof_code(stack))
    assert confirmed.status_code == 200
    assert confirmed.json()['full_name'] == 'Routing Profile'
    assert confirmed.json()['phone'] == '0900000002'
    assert stack.account.get('/users/me', headers={'Authorization': 'Bearer ' + token(2)}).json()['full_name'] == 'User 2'


def test_legacy_null_route_proof_keeps_the_original_hmac_format():
    user = SimpleNamespace(id=1, email_challenge_id='legacy', pending_email='legacy@example.test',
        email_pending_profile='{}', email_pending_channel=None)
    original = 'email-ownership:v1:1:legacy:legacy@example.test:{}:123456'
    expected = hmac.new(os.environ['JWT_SECRET_KEY'].encode(), original.encode(), hashlib.sha256).hexdigest()
    assert proof.hash_code(user, '123456') == expected


def test_legacy_pending_route_null_can_still_be_confirmed(stack, routing_user):
    pending = start_proof(stack)
    value = proof_code(stack)
    with SessionLocal.begin() as db:
        user = db.get(User, 1)
        user.email_pending_channel = None
        user.email_code_hash = proof.hash_code(user, value)
    assert confirm_proof(stack, pending.json()['email_verification']['challenge_id'], value).status_code == 200


def test_smtp_only_migration_revokes_mailpit_proofs_and_preserves_real_email_ownership():
    from services.account.migrate import smtp_only_accounts
    engine = create_engine('sqlite+pysqlite:///:memory:')
    Base.metadata.create_all(engine)
    verified_at = utcnow()
    try:
        with Session(engine) as db, db.begin():
            for number, channel in enumerate(('mailpit', 'configured', 'smtp'), 1):
                db.add(User(id=number, username=f'owner{number}', password_hash='preserved-hash',
                    full_name=f'Owner {number}', email=f'owner{number}@example.test',
                    email_channel=channel, email_verified_at=verified_at,
                    pending_email=f'pending{number}@example.test', email_challenge_id=f'old-{number}',
                    email_code_hash='old-hash', email_pending_channel=channel,
                    email_pending_profile='{}', email_code_attempts=2))
        with engine.begin() as connection:
            smtp_only_accounts(connection)
            smtp_only_accounts(connection)
        with Session(engine) as db:
            users = list(db.scalars(select(User).order_by(User.id)))
            assert all(user.email_channel == 'smtp' for user in users)
            assert [(user.email, user.password_hash) for user in users] == [
                (f'owner{number}@example.test', 'preserved-hash') for number in range(1, 4)]
            assert users[0].email_verified_at is None
            assert users[0].pending_email is None and users[0].email_code_hash is None
            assert users[0].email_challenge_id is None and users[0].email_pending_channel is None
            assert users[0].email_pending_profile is None and users[0].email_code_attempts == 0
            assert users[1].email_verified_at == users[2].email_verified_at == verified_at
    finally:
        engine.dispose()


def test_two_users_share_tuition_but_receive_codes_only_at_their_updated_emails(stack, transport):
    from services.account.models import Account
    from services.payment.outbox import dispatch_once

    # Exercise the actual MIME/envelope transport rather than the Stack mail stub.
    stack.account.app.dependency_overrides[mailer.get_mailer] = lambda: mailer.Mailer()
    stack.payment.app.dependency_overrides[mailer.get_mailer] = lambda: mailer.Mailer()
    hashed = password_hasher.hash(PASSWORD)
    with SessionLocal.begin() as db:
        for number in (1, 2):
            user = db.get(User, number)
            user.password_hash = hashed
            user.email_channel = 'smtp'
    cases = []
    for number in (1, 2):
        recipient = f'updated-owner{number}@example.test'
        headers = {'Authorization': 'Bearer ' + token(number)}
        pending = stack.account.put('/users/me', headers=headers, json={
            'full_name': f'Updated Owner {number}', 'email': recipient,
            'phone': f'090000000{number}', 'identity_number': f'00000000000{number}',
            'current_password': PASSWORD})
        assert pending.status_code == 202
        assert pending.json()['email'] == f'user{number}@example.test'
        sent = [row for row in transport if row['event'] == 'send'][-1]
        assert sent['to'] == recipient and sent['recipients'] == [recipient]
        code = re.search(r':\s*(\d{6})', sent['body']).group(1)
        confirmed = stack.account.post('/users/me/email-verification/confirm', headers=headers,
            json={'challenge_id': pending.json()['email_verification']['challenge_id'], 'code': code})
        assert confirmed.status_code == 200 and confirmed.json()['email'] == recipient
        created = stack.payment.post('/api/v1/payments',
            headers=headers | {'Idempotency-Key': str(uuid4())},
            json={'mssv': 'SV2026001', 'selection_mode': 'ALL_UNPAID', 'terms_accepted': True})
        assert created.status_code == 201 and created.json()['payer_email'] == recipient
        key = created.json()['payment_id']
        challenge = stack.payment.post(f'/api/v1/payments/{key}/send-otp', headers=headers)
        assert challenge.status_code == 202
        sent = [row for row in transport if row['event'] == 'send'][-1]
        assert sent['to'] == recipient and sent['recipients'] == [recipient]
        payment_code = re.search(r'Mã OTP của bạn:\s*(\d{6})', sent['body']).group(1)
        cases.append({'key': key, 'headers': headers, 'recipient': recipient,
            'challenge': challenge.json()['challenge_id'], 'code': payment_code})

    assert cases[0]['code'] != cases[1]['code']
    for case in cases:
        verified = stack.payment.post(f"/api/v1/payments/{case['key']}/verify-otp", headers=case['headers'],
            json={'challenge_id': case['challenge'], 'otp': case['code']})
        assert verified.status_code == 200
    first = stack.payment.post(f"/api/v1/payments/{cases[0]['key']}/process", headers=cases[0]['headers'])
    second = stack.payment.post(f"/api/v1/payments/{cases[1]['key']}/process", headers=cases[1]['headers'])
    assert first.json()['status'] == 'SUCCEEDED'
    assert second.status_code == 409 and second.json()['status'] == 'FAILED'
    assert dispatch_once(mailer.Mailer()) == 1
    sent = [row for row in transport if row['event'] == 'send']
    assert [row['recipients'] for row in sent] == [
        [cases[0]['recipient']], [cases[0]['recipient']],
        [cases[1]['recipient']], [cases[1]['recipient']], [cases[0]['recipient']]]
    assert all(row['to'] == row['recipients'][0] for row in sent)
    assert all(row['from'] == 'iBanking <sender@example.test>' for row in sent)
    with SessionLocal() as db:
        assert db.get(Account, 1).balance == Decimal('1000000.00')
        assert db.get(Account, 2).balance == Decimal('10000000.00')
