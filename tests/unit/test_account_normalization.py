"""ID remapping preserves identity, ownership and financial snapshots."""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
import hashlib
import json

import pytest

from infra.docker import normalize_accounts


@pytest.fixture
def snapshot():
    users = [{'id': number, 'username': 'huy' if number == 1 else f'demo{number-1:02d}',
        'password_hash': f'private-hash-{number}', 'email_code_hash': None,
        'email_verified_at': None} for number in range(1, 12)]
    # Another user's pending proof remains valid because their ID stays 2.
    users[1]['email_code_hash'] = 'pending-proof-of-demo01'
    users.append({'id': 10002, 'username': 'huy2', 'password_hash': 'private-huy2-hash',
        'email': 'second@example.test', 'email_code_hash': None,
        'email_verified_at': datetime(2026, 11, 7, 12)})
    accounts = [{'id': row['id'], 'user_id': row['id'], 'account_number': f'ACCOUNT-{row["id"]}',
        'balance': Decimal('8000000.00') if row['id'] == 10002 else Decimal('10000000.00'),
        'status': 'ACTIVE'} for row in users]
    return {'users': users, 'accounts': accounts,
        'entries': [{'id': 10002, 'payment_id': 'paid-uuid', 'account_id': 10002,
            'entry_type': 'DEBIT', 'amount': Decimal('2000000.00')}],
        'cancellations': [{'payment_id': 'cancelled-uuid', 'account_id': 10002,
            'payer_user_id': 10002, 'amount': Decimal('500000.00')}],
        'payments': [{'payment_id': 'paid-uuid', 'payer_user_id': 10002, 'account_id': 10002,
            'request_hash': 'old-fingerprint', 'mssv': 'SV20261012', 'selection_mode': 'ALL_UNPAID',
            'status': 'SUCCEEDED', 'total_amount': Decimal('2000000.00'),
            'completed_at': datetime(2026, 11, 7, 12, 42, 28)}]}


def test_huy2_becomes_12_and_all_persisted_references_follow_without_changing_money(snapshot):
    original = deepcopy(snapshot)
    plan = normalize_accounts.build_plan(snapshot)
    rows = plan['rows']
    assert snapshot == original
    assert plan['user_ids'][10002] == plan['account_ids'][10002] == 12
    assert [row['id'] for row in rows['users']] == list(range(1, 13))
    assert [row['id'] for row in rows['accounts']] == list(range(1, 13))
    assert rows['users'][-1] == dict(snapshot['users'][-1], id=12)
    assert rows['users'][1]['email_code_hash'] == 'pending-proof-of-demo01'
    assert rows['accounts'][-1] == dict(snapshot['accounts'][-1], id=12, user_id=12)
    assert rows['entries'][0] == dict(snapshot['entries'][0], account_id=12)
    assert rows['cancellations'][0] == dict(snapshot['cancellations'][0], account_id=12, payer_user_id=12)
    payment = rows['payments'][0]
    expected_hash = hashlib.sha256(json.dumps({'user_id': 12, 'mssv': 'SV20261012',
        'selection_mode': 'ALL_UNPAID', 'invoice_ids': []}, sort_keys=True).encode()).hexdigest()
    assert payment == dict(snapshot['payments'][0], account_id=12, payer_user_id=12, request_hash=expected_hash)


def test_remapping_is_repeatable_without_new_users_or_changes_to_paid_history(snapshot):
    first = normalize_accounts.build_plan(snapshot)
    second = normalize_accounts.build_plan(first['rows'])
    assert first['rows'] == second['rows']
    assert all(old == new for old, new in second['user_ids'].items())
    assert all(old == new for old, new in second['account_ids'].items())


def test_pending_email_proof_on_the_remapped_user_blocks_the_rewrite(snapshot):
    snapshot['users'][-1]['email_code_hash'] = 'bound-to-old-user-id'
    with pytest.raises(ValueError, match='pending email proof'):
        normalize_accounts.build_plan(snapshot)


@pytest.mark.parametrize('status', ['PENDING_OTP', 'OTP_VERIFIED', 'PROCESSING', 'PENDING_RECONCILIATION'])
def test_in_flight_payment_on_the_remapped_account_blocks_the_rewrite(snapshot, status):
    snapshot['payments'][0]['status'] = status
    with pytest.raises(ValueError, match='pending payments'):
        normalize_accounts.build_plan(snapshot)


def test_an_unchanged_account_keeps_its_pending_payment_and_existing_request_hash(snapshot):
    snapshot['payments'].append(dict(snapshot['payments'][0], payment_id='unchanged-payment',
        payer_user_id=1, account_id=1, status='PENDING_OTP', request_hash='original-unchanged-fingerprint'))
    plan = normalize_accounts.build_plan(snapshot)
    assert plan['rows']['payments'][1] == snapshot['payments'][1]


@pytest.mark.parametrize('table,change', [
    ('accounts', {'user_id': 99999}),
    ('entries', {'account_id': 99999}),
    ('payments', {'payer_user_id': 1}),
    ('payments', {'account_id': 99999}),
    ('cancellations', {'payer_user_id': 1}),
])
def test_unknown_or_mismatched_ownership_blocks_the_rewrite(snapshot, table, change):
    snapshot[table][-1].update(change)
    with pytest.raises(ValueError):
        normalize_accounts.build_plan(snapshot)


def test_non_local_environment_is_rejected_before_any_connection(monkeypatch):
    monkeypatch.setenv('DB_SERVER', 'production.invalid')
    monkeypatch.setattr(normalize_accounts, 'create_engine', lambda *args, **kwargs: pytest.fail('must not connect'))
    with pytest.raises(RuntimeError):
        normalize_accounts.normalize('ibanking-demo')


def test_confirmation_is_checked_before_any_connection(monkeypatch):
    for key, value in {'DB_SERVER': 'sqlserver,1433', 'DB_NAME': 'account_db',
        'PAYMENT_DB_NAME': 'payment_db', 'TUITION_DB_NAME': 'tuition_db'}.items():
        monkeypatch.setenv(key, value)
    for key in ('ACCOUNT_DATABASE_URL', 'PAYMENT_DATABASE_URL', 'TUITION_DATABASE_URL'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(normalize_accounts, 'create_engine', lambda *args, **kwargs: pytest.fail('must not connect'))
    with pytest.raises(ValueError, match='confirmation'):
        normalize_accounts.normalize('wrong-target')
