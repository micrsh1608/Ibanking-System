from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from services.account.database import SessionLocal as AccountSession
from services.account.models import Account, AccountEntry
from services.payment.database import SessionLocal as PaymentSession
from services.payment.models.payment import PaymentTransaction
from services.tuition.database import SessionLocal as TuitionSession
from services.tuition.models import TuitionInvoice
from tests.unit.conftest import token


def balance_and_entries():
    with AccountSession() as db:
        return db.get(Account, 1).balance, list(db.scalars(select(AccountEntry)))


def test_auth_ownership_and_server_controlled_snapshot(stack):
    assert stack.payment.get('/api/v1/payments').status_code == 401
    assert stack.payment.post('/api/v1/payments', headers={**stack.headers, 'Idempotency-Key': str(uuid4())},
        json={'mssv': 'SV2026001', 'selection_mode': 'ALL_UNPAID', 'terms_accepted': True, 'amount': '1.00'}).status_code == 422
    payment = stack.create()
    key = payment['payment_id']
    assert Decimal(payment['total_amount']) == Decimal('9000000.00')
    assert [item['invoice_id'] for item in payment['items']] == [1, 2, 3]
    replay = stack.payment.post('/api/v1/payments', headers={**stack.headers, 'Idempotency-Key': key},
        json={'mssv': 'SV2026001', 'selection_mode': 'ALL_UNPAID', 'terms_accepted': True})
    assert replay.status_code == 200
    assert replay.json() == payment
    changed = stack.payment.post('/api/v1/payments', headers={**stack.headers, 'Idempotency-Key': key},
        json={'mssv': 'ANOTHER_MSSV', 'selection_mode': 'ALL_UNPAID', 'terms_accepted': True})
    assert changed.status_code == 409
    other = {'Authorization': 'Bearer ' + token(2)}
    for suffix in ('', '/send-otp', '/process'):
        request = stack.payment.get if not suffix else stack.payment.post
        assert request(f'/api/v1/payments/{key}{suffix}', headers=other).status_code == 404
    assert stack.payment.get('/api/v1/payments', headers=other).json()['items'] == []


@pytest.mark.parametrize('single_fee,total', [(True, '2000000.00'), (False, '9000000.00')])
def test_success_and_repeated_process_only_debit_once(stack, single_fee, total):
    if single_fee:
        with TuitionSession.begin() as db:
            db.execute(delete(TuitionInvoice).where(TuitionInvoice.id != 1))
    payment = stack.create()
    key = payment['payment_id']
    assert stack.process(key).status_code == 409
    stack.verify(key)
    assert stack.process(key).json()['status'] == 'SUCCEEDED'
    assert stack.process(key).json()['status'] == 'SUCCEEDED'
    balance, entries = balance_and_entries()
    assert balance == Decimal('10000000.00') - Decimal(total)
    assert len(entries) == 1 and entries[0].payment_id == key
    with TuitionSession() as db:
        assert db.get(TuitionInvoice, 1).paid_payment_id == key
        if not single_fee:
            assert all(db.get(TuitionInvoice, value).status == 'PAID' for value in (2, 3))


def test_insufficient_balance_releases_entire_group(stack):
    payment = stack.create()
    with AccountSession.begin() as db:
        db.get(Account, 1).balance = Decimal('1000000.00')
    stack.verify(payment['payment_id'])
    response = stack.process(payment['payment_id'])
    assert response.status_code == 409 and response.json()['status'] == 'FAILED'
    assert balance_and_entries() == (Decimal('1000000.00'), [])
    with TuitionSession() as db:
        assert all(db.get(TuitionInvoice, value).status == 'UNPAID' for value in (1, 2, 3))


@pytest.mark.parametrize('service,path_suffix,phase', [('account', '/internal/accounts/debit', 'DEBIT'),
    ('tuition', '/finalize', 'FINALIZE')])
def test_lost_reply_after_commit_recovers_without_double_effect(stack, service, path_suffix, phase):
    key = stack.create()['payment_id']
    stack.verify(key)
    path = path_suffix if service == 'account' else f'/internal/tuition/reservations/{key}' + path_suffix
    stack.services.faults[(service, path)] = 'after'
    response = stack.process(key)
    assert response.status_code == 202
    assert response.json()['status'] == 'PENDING_RECONCILIATION'
    assert response.json()['phase'] == phase
    assert stack.process(key).json()['status'] == 'SUCCEEDED'
    balance, entries = balance_and_entries()
    assert balance == Decimal('1000000.00') and len(entries) == 1


@pytest.mark.parametrize('fault,expected', [('conflict', 'REFUNDED'), ('conflict_after', 'SUCCEEDED')])
def test_fence_before_refund_and_never_refund_paid_invoices(stack, fault, expected):
    key = stack.create()['payment_id']
    stack.verify(key)
    stack.services.faults[('tuition', f'/internal/tuition/reservations/{key}/finalize')] = fault
    assert stack.process(key).json()['status'] == expected
    balance, entries = balance_and_entries()
    assert balance == Decimal('10000000.00' if expected == 'REFUNDED' else '1000000.00')
    assert len(entries) == (2 if expected == 'REFUNDED' else 1)


def test_persisted_intent_is_recovered_by_worker(stack, monkeypatch):
    from services.payment import recovery
    from services.payment.coordinator import process_payment
    from shared.time import utcnow
    key = stack.create()['payment_id']
    stack.verify(key)
    stack.services.faults[('account', '/internal/accounts/debit')] = 'after'
    assert stack.process(key).status_code == 202
    with PaymentSession.begin() as db:
        db.get(PaymentTransaction, key).next_retry_at = utcnow()
    monkeypatch.setattr(recovery, 'process_payment', lambda value: process_payment(value, stack.services))
    assert recovery.reconcile_once() == 1
    assert stack.payment.get(f'/api/v1/payments/{key}', headers=stack.headers).json()['status'] == 'SUCCEEDED'
    assert len(balance_and_entries()[1]) == 1


def test_otp_attempts_persist_and_verified_code_cannot_be_reused(stack):
    key = stack.create()['payment_id']
    challenge = stack.payment.post(f'/api/v1/payments/{key}/send-otp', headers=stack.headers).json()
    assert 'otp' not in challenge
    assert stack.payment.post(f'/api/v1/payments/{key}/send-otp', headers=stack.headers).status_code == 429
    for _ in range(5):
        assert stack.payment.post(f'/api/v1/payments/{key}/verify-otp', headers=stack.headers,
            json={'challenge_id': challenge['challenge_id'], 'otp': '000000'}).status_code == 400
    assert stack.payment.post(f'/api/v1/payments/{key}/verify-otp', headers=stack.headers,
        json={'challenge_id': challenge['challenge_id'], 'otp': '123456'}).status_code == 429
    other = stack.create()['payment_id']
    stack.verify(other)
    assert stack.payment.post(f'/api/v1/payments/{other}/verify-otp', headers=stack.headers,
        json={'challenge_id': challenge['challenge_id'], 'otp': '123456'}).status_code == 409


def test_cancel_before_debit_is_a_durable_fence(stack):
    key = str(uuid4())
    body = {'payment_id': key, 'account_id': 1, 'payer_user_id': 1, 'amount': '2000000.00'}
    assert stack.account.post('/internal/accounts/cancel', headers=stack.internal, json=body).json()['status'] == 'CANCELLED'
    assert stack.account.post('/internal/accounts/debit', headers=stack.internal, json=body).json()['status'] == 'CANCELLED'
    changed = {**body, 'amount': '3000000.00'}
    assert stack.account.post('/internal/accounts/debit', headers=stack.internal, json=changed).status_code == 409
    assert balance_and_entries() == (Decimal('10000000.00'), [])
