from uuid import uuid4

from services.tuition.database import SessionLocal
from services.tuition.models import TuitionInvoice


def reserve(stack, key, ids, total):
    return stack.tuition.post('/internal/tuition/reservations', headers=stack.internal, json={
        'payment_id': key, 'mssv': 'SV2026001',
        'items': [{'invoice_id': value, 'version': 1} for value in ids], 'expected_total': total})


def action(stack, key, verb):
    return stack.tuition.post(f'/internal/tuition/reservations/{key}/{verb}', headers=stack.internal)


def test_group_is_atomic_and_overlaps_do_not_partially_reserve(stack):
    first, other = str(uuid4()), str(uuid4())
    assert reserve(stack, first, [1, 2], '5000000.00').status_code == 200
    assert reserve(stack, first, [2, 1], '5000000.0').status_code == 200
    assert reserve(stack, first, [1], '2000000.00').status_code == 409
    assert reserve(stack, other, [2, 3], '7000000.00').status_code == 409
    with SessionLocal() as db:
        assert db.get(TuitionInvoice, 3).status == 'UNPAID'
    assert action(stack, first, 'finalize').json()['status'] == 'PAID'
    assert action(stack, first, 'finalize').json()['status'] == 'PAID'
    assert action(stack, first, 'release').status_code == 409


def test_release_is_idempotent_and_fences_late_reserve_and_finalize(stack):
    key = str(uuid4())
    assert reserve(stack, key, [1, 2], '5000000.00').status_code == 200
    assert action(stack, key, 'release').json()['status'] == 'RELEASED'
    assert action(stack, key, 'release').json()['status'] == 'RELEASED'
    assert reserve(stack, key, [1, 2], '5000000.00').status_code == 409
    assert action(stack, key, 'finalize').status_code == 409
    # An old snapshot must not be accepted under a new UUID after a reservation cycle.
    assert reserve(stack, str(uuid4()), [1], '2000000.00').status_code == 409
    empty = str(uuid4())
    assert action(stack, empty, 'release').json()['status'] == 'RELEASED'
    assert reserve(stack, empty, [3], '4000000.00').status_code == 409


def test_internal_auth_and_total_are_checked(stack):
    assert stack.tuition.get('/internal/tuition/invoices?mssv=SV2026001').status_code == 401
    assert reserve(stack, str(uuid4()), [1, 2], '1.00').status_code == 409
    with SessionLocal() as db:
        assert db.get(TuitionInvoice, 1).status == 'UNPAID'
