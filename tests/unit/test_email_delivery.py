from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, select

from services.payment.database import SessionLocal
from services.payment.models.payment import EmailOutbox, PaymentTransaction
from services.payment.outbox import dispatch_once
from shared.time import utcnow


def test_otp_is_mailed_bound_to_snapshot_and_never_returned_or_logged(stack, capsys):
    key = stack.create()['payment_id']
    challenge = stack.payment.post(f'/api/v1/payments/{key}/send-otp', headers=stack.headers)
    assert challenge.status_code == 202
    assert challenge.json()['delivery_address'] == 'u***@example.test'
    assert challenge.json()['demo_mode'] is False
    assert '123456' not in challenge.text
    assert '123456' not in capsys.readouterr().out
    restored = stack.payment.get(f'/api/v1/payments/{key}', headers=stack.headers).json()['active_challenge']
    assert restored['challenge_id'] == challenge.json()['challenge_id']
    assert '123456' not in str(restored)
    message = stack.mailer.messages[-1]
    assert message['recipient'] == 'user1@example.test'
    for text in (key, '123456', 'HK1', 'HK2', 'HK3', '9.000.000,00', 'SV2026001'):
        assert text in message['body']


def test_smtp_failure_invalidates_challenge_and_allows_resending(stack):
    key = stack.create()['payment_id']
    stack.mailer.fail = True
    assert stack.payment.post(f'/api/v1/payments/{key}/send-otp', headers=stack.headers).status_code == 503
    with SessionLocal() as db:
        payment = db.get(PaymentTransaction, key)
        assert payment.otp_hash is None and payment.otp_verified_at is None
    stack.mailer.fail = False
    stack.verify(key)


def test_resend_revokes_previous_challenge_and_verification(stack):
    key = stack.create()['payment_id']
    stack.verify(key)
    with SessionLocal.begin() as db:
        previous = db.get(PaymentTransaction, key)
        old = previous.challenge_id
        previous.otp_last_sent_at = utcnow() - timedelta(seconds=61)
    new = stack.payment.post(f'/api/v1/payments/{key}/send-otp', headers=stack.headers).json()
    assert new['challenge_id'] != old
    assert stack.process(key).status_code == 409
    assert stack.payment.post(f'/api/v1/payments/{key}/verify-otp', headers=stack.headers,
        json={'challenge_id': old, 'otp': '123456'}).status_code == 400


def test_receipt_retry_never_repeats_payment_or_duplicate_outbox_event(stack):
    from tests.unit.test_payment_flow import balance_and_entries
    key = stack.create()['payment_id']
    stack.verify(key)
    result = stack.process(key)
    assert result.status_code == 200
    assert result.json()['receipt_status'] == 'PENDING'
    assert result.json()['completed_at'] is not None
    stack.mailer.fail = True
    assert dispatch_once(stack.mailer) == 0
    with SessionLocal() as db:
        pending = db.scalar(select(EmailOutbox).where(EmailOutbox.payment_id == key))
        assert pending.status == 'PENDING' and pending.attempts == 1 and pending.next_attempt_at > utcnow()
    assert balance_and_entries()[0] == Decimal('1000000.00')
    assert len(balance_and_entries()[1]) == 1
    assert stack.process(key).json()['status'] == 'SUCCEEDED'
    with SessionLocal.begin() as db:
        assert db.scalar(select(func.count()).select_from(EmailOutbox)) == 1
        db.scalar(select(EmailOutbox)).next_attempt_at = utcnow()
    stack.mailer.fail = False
    assert dispatch_once(stack.mailer) == 1
    assert dispatch_once(stack.mailer) == 0
    assert len(balance_and_entries()[1]) == 1
    receipt = stack.mailer.messages[-1]
    assert receipt['recipient'] == 'user1@example.test' and key in receipt['body']
    assert 'HK1' in receipt['body'] and 'HK2' in receipt['body'] and 'THÀNH CÔNG' in receipt['body']
    assert stack.payment.get(f'/api/v1/payments/{key}', headers=stack.headers).json()['receipt_status'] == 'SENT'
