"""Reference-preserving rewrite checks, independent of the private SQL Server."""
from copy import deepcopy
from decimal import Decimal

import pytest
from sqlalchemy import select

from infra.docker.normalize_tuition import build_plan, fingerprint
from services.tuition.models import Student, TuitionInvoice
from services.tuition.seed import DemoTuitionSeedError, seed_demo_students


@pytest.fixture
def snapshot():
    return {
        'students': [
            {'id': 1, 'mssv': 'SV2026001', 'full_name': 'Sinh viên Demo'},
            {'id': 2, 'mssv': 'DEMO20261105', 'full_name': 'Sinh viên trình diễn'},
            {'id': 1006, 'mssv': 'DEMO05', 'full_name': 'iBanking demo catalog: DEMO05'},
            {'id': 2002, 'mssv': 'SV20261001', 'full_name': 'Nguyễn Minh An'},
        ],
        'invoices': [
            {'id': 1, 'student_id': 1, 'semester': '2026-2027-HK1', 'amount_due': Decimal('2000000.00'),
             'status': 'PAID', 'version': 3, 'paid_payment_id': 'paid-uuid'},
            {'id': 1002, 'student_id': 1, 'semester': 'TEST-2026-HK3', 'amount_due': Decimal('100000.00'),
             'status': 'PAID', 'version': 3, 'paid_payment_id': 'paid-uuid'},
            {'id': 2003, 'student_id': 2, 'semester': 'DEMO-HK1', 'amount_due': Decimal('400000.00'),
             'status': 'UNPAID', 'version': 1, 'paid_payment_id': None},
            {'id': 3007, 'student_id': 1006, 'semester': 'CATALOG-HK1', 'amount_due': Decimal('1000000.00'),
             'status': 'UNPAID', 'version': 1, 'paid_payment_id': None},
            {'id': 4002, 'student_id': 2002, 'semester': 'CATALOG-HK1', 'amount_due': Decimal('2500000.00'),
             'status': 'UNPAID', 'version': 1, 'paid_payment_id': None},
        ],
        'payments': [{'payment_id': 'paid-uuid', 'mssv': 'SV2026001', 'student_name': 'Sinh viên Demo',
            'status': 'SUCCEEDED', 'payer_user_id': 1, 'selection_mode': 'ALL_UNPAID',
            'request_hash': 'old-payment-hash', 'total_amount': Decimal('2100000.00')}],
        'payment_items': [
            {'id': 1, 'payment_id': 'paid-uuid', 'invoice_id': 1, 'invoice_version': 1,
             'amount': Decimal('2000000.00'), 'semester': '2026-2027-HK1'},
            {'id': 1002, 'payment_id': 'paid-uuid', 'invoice_id': 1002, 'invoice_version': 1,
             'amount': Decimal('100000.00'), 'semester': 'TEST-2026-HK3'},
        ],
        'reservations': [{'payment_id': 'paid-uuid', 'mssv': 'SV2026001', 'status': 'PAID',
            'request_hash': 'old-reservation-hash', 'total_amount': Decimal('2100000.00')}],
        'reservation_items': [
            {'id': 1, 'payment_id': 'paid-uuid', 'invoice_id': 1, 'amount': Decimal('2000000.00')},
            {'id': 1002, 'payment_id': 'paid-uuid', 'invoice_id': 1002, 'amount': Decimal('100000.00')},
        ],
    }


def test_rewrite_assigns_readable_codes_and_consecutive_ids_preserving_history(snapshot):
    original = deepcopy(snapshot)
    plan = build_plan(snapshot)
    rows = plan['rows']
    assert snapshot == original
    assert [(row['id'], row['mssv']) for row in rows['students']] == [
        (1, 'SV20261001'), (2, 'SV20261007'), (3, 'SV20261013'), (4, 'SV20261014')]
    assert rows['students'][1]['full_name'] == 'Đặng Minh Quân'
    assert [row['id'] for row in rows['invoices']] == [1, 2, 3, 4, 5]
    assert [row['student_id'] for row in rows['invoices']] == [1, 2, 3, 3, 4]
    assert rows['payment_items'][1]['invoice_id'] == rows['reservation_items'][1]['invoice_id'] == 4
    for before in snapshot['invoices']:
        after = next(row for row in rows['invoices'] if row['id'] == plan['invoice_ids'][before['id']])
        assert (after['amount_due'], after['status'], after['paid_payment_id'], after['version']) == (
            before['amount_due'], before['status'], before['paid_payment_id'], before['version'])
    payment = rows['payments'][0]
    assert payment['payment_id'] == 'paid-uuid' and payment['status'] == 'SUCCEEDED'
    assert payment['mssv'] == 'SV20261013' and payment['student_name'] == 'Lê Minh Khang'
    assert payment['request_hash'] == fingerprint({'user_id': 1, 'mssv': 'SV20261013',
        'selection_mode': 'ALL_UNPAID', 'invoice_ids': []})
    assert rows['reservations'][0]['request_hash'] == fingerprint({'mssv': 'SV20261013',
        'items': [(3, 1), (4, 1)], 'total': '2100000.00'})


def test_plan_is_repeatable_without_adding_debt_or_changing_ids(snapshot):
    first = build_plan(snapshot)
    second = build_plan(first['rows'])
    assert first['rows'] == second['rows']
    assert all(old == new for old, new in second['invoice_ids'].items())


@pytest.mark.parametrize('table,status', [
    ('payments', 'PENDING_OTP'), ('payments', 'OTP_VERIFIED'), ('payments', 'PROCESSING'),
    ('payments', 'PENDING_RECONCILIATION'), ('invoices', 'RESERVED'), ('reservations', 'RESERVED'),
])
def test_pending_work_blocks_rewrite(snapshot, table, status):
    snapshot[table][0]['status'] = status
    with pytest.raises(ValueError, match='pending payments'):
        build_plan(snapshot)


def test_conflicting_replacement_code_is_never_merged(snapshot):
    snapshot['students'].append({'id': 2003, 'mssv': 'SV20261007', 'full_name': 'Another student'})
    with pytest.raises(ValueError, match='no students were merged'):
        build_plan(snapshot)


def test_non_catalog_owner_is_never_renamed(snapshot):
    snapshot['students'][2]['full_name'] = 'Another owner'
    with pytest.raises(ValueError, match='not owned'):
        build_plan(snapshot)


@pytest.mark.parametrize('change', [{'invoice_id': 9999}, {'amount': Decimal('1.00')}, {'payment_id': 'unknown'}])
def test_invalid_payment_reference_blocks_rewrite(snapshot, change):
    snapshot['payment_items'][0].update(change)
    with pytest.raises(ValueError, match='does not match'):
        build_plan(snapshot)


def test_duplicate_semester_blocks_rewrite(snapshot):
    duplicate = dict(snapshot['invoices'][-1], id=4003, semester='2026-2027-HK1')
    snapshot['invoices'].append(duplicate)
    with pytest.raises(ValueError, match='duplicate invoices'):
        build_plan(snapshot)


def test_seed_refuses_to_duplicate_legacy_students():
    from sqlalchemy import create_engine, func
    from sqlalchemy.orm import sessionmaker
    from services.tuition.database import Base
    engine = create_engine('sqlite+pysqlite:///:memory:')
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    try:
        with sessions.begin() as db:
            db.add(Student(mssv='DEMO05', full_name='iBanking demo catalog: DEMO05'))
        with pytest.raises(DemoTuitionSeedError, match='NormalizeTuition'):
            seed_demo_students(sessions)
        with sessions() as db:
            assert db.scalar(select(func.count()).select_from(Student)) == 1
            assert db.scalar(select(func.count()).select_from(TuitionInvoice)) == 0
    finally:
        engine.dispose()
