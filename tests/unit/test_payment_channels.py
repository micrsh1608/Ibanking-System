from contextlib import contextmanager
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import create_engine, func, select

from services.account.database import SessionLocal as AccountSession
from services.account.models import Account, AccountEntry, User
from services.payment.database import SessionLocal as PaymentSession
from services.payment.models.payment import EmailOutbox, PaymentTransaction
from services.payment.outbox import dispatch_once
from services.tuition.database import SessionLocal as TuitionSession
from services.tuition.models import Reservation, TuitionInvoice
from shared.time import utcnow
from tests.unit.conftest import token


def payer_delivery(stack, monkeypatch, channel):
    original = stack.services.payer
    current = {'channel': channel}

    def payer(value):
        user, account = original(value)
        user['email_delivery'] = current['channel']
        return user, account

    monkeypatch.setattr(stack.services, 'payer', payer)
    return current


def assert_no_money_or_tuition_effects():
    with AccountSession() as db:
        assert db.get(Account, 1).balance == Decimal('10000000.00')
        assert db.scalar(select(func.count()).select_from(AccountEntry)) == 0
    with TuitionSession() as db:
        assert db.scalar(select(func.count()).select_from(Reservation)) == 0
        assert all(row.status == 'UNPAID' for row in db.scalars(select(TuitionInvoice)))
    with PaymentSession() as db:
        assert db.scalar(select(func.count()).select_from(EmailOutbox)) == 0


@pytest.mark.parametrize('unavailable_channel', ['mailpit', 'not_configured'])
def test_otp_uses_smtp_snapshot_and_unavailable_route_blocks_stale_draft(stack, monkeypatch, unavailable_channel):
    monkeypatch.setenv('SMTP_HOST', 'smtp.unit-tests.invalid')
    current = payer_delivery(stack, monkeypatch, 'smtp')
    payment = stack.create()
    key = payment['payment_id']
    assert payment['email_delivery'] == 'smtp'
    response = stack.payment.post(f'/api/v1/payments/{key}/send-otp', headers=stack.headers)
    assert response.status_code == 202
    challenge = response.json()
    assert challenge['email_delivery'] == 'smtp'
    assert stack.mailer.messages[-1]['channel'] == 'smtp'
    restored = stack.payment.get(f'/api/v1/payments/{key}', headers=stack.headers).json()
    assert restored['active_challenge']['email_delivery'] == 'smtp'
    current['channel'] = unavailable_channel
    assert stack.payment.post(f'/api/v1/payments/{key}/verify-otp', headers=stack.headers,
        json={'challenge_id': challenge['challenge_id'], 'otp': '123456'}).status_code == 503
    assert stack.payment.post(f'/api/v1/payments/{key}/send-otp', headers=stack.headers).status_code == 503
    with PaymentSession() as db:
        assert db.get(PaymentTransaction, key).email_channel == 'smtp'
    assert len(stack.mailer.messages) == 1
    assert_no_money_or_tuition_effects()


def test_changed_channel_also_blocks_first_process_after_verification(stack, monkeypatch):
    monkeypatch.setenv('SMTP_HOST', 'smtp.unit-tests.invalid')
    current = payer_delivery(stack, monkeypatch, 'smtp')
    key = stack.create()['payment_id']
    stack.verify(key)
    current['channel'] = 'not_configured'
    assert stack.process(key).status_code == 503
    assert_no_money_or_tuition_effects()


def test_legacy_payer_without_delivery_still_snapshots_real_smtp(stack, monkeypatch):
    monkeypatch.setenv('SMTP_HOST', 'smtp.unit-tests.invalid')
    original = stack.services.payer

    def payer(value):
        user, account = original(value)
        user.pop('email_delivery', None)
        return user, account

    monkeypatch.setattr(stack.services, 'payer', payer)
    key = stack.create()['payment_id']
    with PaymentSession() as db:
        assert db.get(PaymentTransaction, key).email_channel == 'smtp'
    stack.verify(key)
    assert stack.mailer.messages[-1]['channel'] == 'smtp'


def test_unconfigured_account_route_cannot_fall_back_to_global_smtp(stack, monkeypatch):
    # A usable global SMTP server must not bypass an unavailable per-user route.
    monkeypatch.setenv('SMTP_HOST', 'smtp.unit-tests.invalid')
    with AccountSession.begin() as db:
        db.get(User, 1).email_channel = 'mailpit'
    assert stack.account.get('/users/me', headers=stack.headers).json()['email_delivery'] == 'not_configured'
    result = stack.payment.post('/api/v1/payments', headers=stack.headers | {'Idempotency-Key': str(uuid4())},
        json={'mssv': 'SV2026001', 'selection_mode': 'ALL_UNPAID', 'terms_accepted': True})
    assert result.status_code == 503
    assert stack.mailer.messages == []
    with PaymentSession() as db:
        assert db.scalar(select(func.count()).select_from(PaymentTransaction)) == 0
    assert_no_money_or_tuition_effects()


@pytest.mark.parametrize('verified', [False, True])
def test_unavailable_user_route_blocks_otp_and_first_process_without_rerouting(stack, monkeypatch, verified):
    monkeypatch.setenv('SMTP_HOST', 'smtp.unit-tests.invalid')
    current = payer_delivery(stack, monkeypatch, 'smtp')
    key = stack.create()['payment_id']
    challenge = stack.payment.post(f'/api/v1/payments/{key}/send-otp', headers=stack.headers).json()
    if verified:
        assert stack.payment.post(f'/api/v1/payments/{key}/verify-otp', headers=stack.headers,
            json={'challenge_id': challenge['challenge_id'], 'otp': '123456'}).status_code == 200
    current['channel'] = 'not_configured'
    assert stack.payment.post(f'/api/v1/payments/{key}/send-otp', headers=stack.headers).status_code == 503
    assert stack.payment.post(f'/api/v1/payments/{key}/verify-otp', headers=stack.headers,
        json={'challenge_id': challenge['challenge_id'], 'otp': '123456'}).status_code == 503
    assert stack.process(key).status_code == 503
    assert len(stack.mailer.messages) == 1 and stack.mailer.messages[0]['channel'] == 'smtp'
    with PaymentSession() as db:
        assert db.get(PaymentTransaction, key).email_channel == 'smtp'
    assert_no_money_or_tuition_effects()


@pytest.mark.parametrize('field', ['email_channel', 'email_delivery'])
def test_client_cannot_choose_payment_mail_transport(stack, field):
    result = stack.payment.post('/api/v1/payments', headers=stack.headers | {'Idempotency-Key': str(uuid4())},
        json={'mssv': 'SV2026001', 'selection_mode': 'ALL_UNPAID', 'terms_accepted': True, field: 'mailpit'})
    assert result.status_code == 422
    with PaymentSession() as db:
        assert db.scalar(select(func.count()).select_from(PaymentTransaction)) == 0


def test_receipt_retry_keeps_original_recipient_and_smtp_snapshot_after_profile_change(stack, monkeypatch):
    monkeypatch.setenv('SMTP_HOST', 'smtp.unit-tests.invalid')
    current = payer_delivery(stack, monkeypatch, 'smtp')
    key = stack.create()['payment_id']
    stack.verify(key)
    assert stack.process(key).json()['status'] == 'SUCCEEDED'
    current['channel'] = 'not_configured'
    stack.mailer.fail = True
    assert dispatch_once(stack.mailer) == 0
    with PaymentSession.begin() as db:
        row = db.scalar(select(EmailOutbox).where(EmailOutbox.payment_id == key))
        assert row.recipient == 'user1@example.test'
        assert row.email_channel == 'smtp' and row.attempts == 1
        row.next_attempt_at = utcnow()
    with AccountSession.begin() as db:
        db.get(User, 1).email = 'updated@example.test'
    stack.mailer.fail = False
    assert dispatch_once(stack.mailer) == 1
    receipt = stack.mailer.messages[-1]
    assert receipt['recipient'] == 'user1@example.test' and receipt['channel'] == 'smtp'
    with AccountSession() as db:
        assert db.get(Account, 1).balance == Decimal('1000000.00')
        assert db.scalar(select(func.count()).select_from(AccountEntry)) == 1
    with PaymentSession() as db:
        assert db.scalar(select(func.count()).select_from(EmailOutbox)) == 1


def test_legacy_mailpit_receipt_is_not_redirected_to_real_smtp(stack, monkeypatch):
    monkeypatch.setenv('SMTP_HOST', 'smtp.unit-tests.invalid')
    payer_delivery(stack, monkeypatch, 'smtp')
    key = stack.create()['payment_id']
    stack.verify(key)
    assert stack.process(key).json()['status'] == 'SUCCEEDED'
    with PaymentSession.begin() as db:
        receipt = db.scalar(select(EmailOutbox).where(EmailOutbox.payment_id == key))
        receipt.email_channel = 'mailpit'
        receipt.recipient = 'historic-mailbox@example.test'
    sent_before = len(stack.mailer.messages)
    assert dispatch_once(stack.mailer) == 0
    assert len(stack.mailer.messages) == sent_before
    with PaymentSession() as db:
        receipt = db.scalar(select(EmailOutbox).where(EmailOutbox.payment_id == key))
        assert receipt.status == 'PENDING' and receipt.attempts == 0
        assert receipt.email_channel == 'mailpit' and receipt.recipient == 'historic-mailbox@example.test'


@pytest.mark.parametrize('verified', [False, True])
def test_cancel_draft_is_owned_idempotent_revokes_otp_and_has_no_remote_effects(stack, verified):
    key = stack.create()['payment_id']
    challenge = stack.payment.post(f'/api/v1/payments/{key}/send-otp', headers=stack.headers).json()
    if verified:
        assert stack.payment.post(f'/api/v1/payments/{key}/verify-otp', headers=stack.headers,
            json={'challenge_id': challenge['challenge_id'], 'otp': '123456'}).status_code == 200
    with PaymentSession() as db:
        row = db.get(PaymentTransaction, key)
        fingerprint, deadline = row.otp_fingerprint, row.otp_expires_at
    other = {'Authorization': 'Bearer ' + token(2)}
    assert stack.payment.post(f'/api/v1/payments/{key}/cancel', headers=other).status_code == 404
    result = stack.payment.post(f'/api/v1/payments/{key}/cancel', headers=stack.headers)
    assert result.status_code == 200
    assert result.json()['status'] == 'FAILED' and result.json()['phase'] == 'DONE'
    assert result.json()['active_challenge'] is None
    assert stack.payment.post(f'/api/v1/payments/{key}/cancel', headers=stack.headers).status_code == 200
    assert stack.payment.post(f'/api/v1/payments/{key}/verify-otp', headers=stack.headers,
        json={'challenge_id': challenge['challenge_id'], 'otp': '123456'}).status_code == 409
    assert stack.payment.post(f'/api/v1/payments/{key}/send-otp', headers=stack.headers).status_code == 409
    assert stack.process(key).status_code == 409
    with PaymentSession() as db:
        row = db.get(PaymentTransaction, key)
        assert row.otp_hash is None and row.challenge_id is None and row.otp_verified_at is None
        assert row.otp_fingerprint == fingerprint and row.otp_expires_at == deadline
    assert_no_money_or_tuition_effects()


@pytest.mark.parametrize('status', ['PROCESSING', 'PENDING_RECONCILIATION', 'SUCCEEDED', 'REFUNDED', 'FAILED'])
def test_cancel_cannot_abort_accepted_intent_or_other_terminal_result(stack, status):
    key = stack.create()['payment_id']
    with PaymentSession.begin() as db:
        row = db.get(PaymentTransaction, key)
        row.status, row.phase, row.error_message = status, 'DEBIT', 'Existing outcome'
    assert stack.payment.post(f'/api/v1/payments/{key}/cancel', headers=stack.headers).status_code == 409
    with PaymentSession() as db:
        row = db.get(PaymentTransaction, key)
        assert (row.status, row.phase, row.error_message) == (status, 'DEBIT', 'Existing outcome')
    assert_no_money_or_tuition_effects()


def test_cancel_uses_same_guard_as_coordinator(stack, monkeypatch):
    from services.payment import routes
    key = stack.create()['payment_id']

    @contextmanager
    def busy(*args):
        yield False

    monkeypatch.setattr(routes, 'session_lock', busy)
    assert stack.payment.post(f'/api/v1/payments/{key}/cancel', headers=stack.headers).status_code == 409
    with PaymentSession() as db:
        assert db.get(PaymentTransaction, key).status == 'PENDING_OTP'


def test_gateway_explicitly_forwards_cancel_without_internal_credentials(stack, monkeypatch):
    from services.account import gateway
    original = httpx.AsyncClient
    seen = []

    def receive(request):
        seen.append(request)
        return httpx.Response(200, json={'status': 'FAILED'})

    monkeypatch.setattr(gateway.httpx, 'AsyncClient',
        lambda **kwargs: original(transport=httpx.MockTransport(receive), **kwargs))
    key = str(uuid4())
    result = stack.account.post(f'/api/v1/payments/{key}/cancel', headers=stack.headers | stack.internal)
    assert result.status_code == 200 and len(seen) == 1
    assert seen[0].url.path == f'/api/v1/payments/{key}/cancel'
    assert 'x-internal-key' not in seen[0].headers


def test_channel_migration_preserves_existing_payments_and_queued_receipts():
    from services.payment.migrate import email_channels
    engine = create_engine('sqlite+pysqlite:///:memory:')
    with engine.begin() as db:
        db.exec_driver_sql('CREATE TABLE payments (payment_id VARCHAR(36), status VARCHAR(32))')
        db.exec_driver_sql("INSERT INTO payments VALUES ('old-payment', 'SUCCEEDED')")
        db.exec_driver_sql('CREATE TABLE email_outbox (id VARCHAR(36), recipient VARCHAR(255), status VARCHAR(12))')
        db.exec_driver_sql("INSERT INTO email_outbox VALUES ('old-receipt', 'original@example.test', 'PENDING')")
        email_channels(db)
        email_channels(db)
        assert db.exec_driver_sql('SELECT * FROM payments').one() == ('old-payment', 'SUCCEEDED', 'configured')
        assert db.exec_driver_sql('SELECT * FROM email_outbox').one() == (
            'old-receipt', 'original@example.test', 'PENDING', 'configured')
