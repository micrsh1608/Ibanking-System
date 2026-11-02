"""Day 02–04 acceptance against the local Docker stack; retains isolated IT_* records.

Run: python -m tests.integration.backend_acceptance
This test restarts only the demo Payment container when checking crash recovery.
"""
import json
import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
PROFILE = os.getenv('IBANKING_TEST_PROFILE', 'demo')
if PROFILE not in {'demo', 'isolated'}:
    raise RuntimeError('Unknown test profile')
PORTS = {'account': 8101, 'payment': 8102, 'tuition': 8103} if PROFILE == 'isolated' else {'account': 8001, 'payment': 8002, 'tuition': 8003}
config = dotenv_values(ROOT / 'infra/env/docker.env')
for name in ('JWT_SECRET_KEY', 'INTERNAL_API_KEY', 'MSSQL_SA_PASSWORD'):
    if not config.get(name) or config[name] == 'CHANGE_ME':
        raise RuntimeError('Configure and start the Docker demo first')
    os.environ[name] = config[name]
# Explicit Docker-only target; never use the private Windows database connection.
os.environ.update(DB_SERVER='127.0.0.1,' + ('14331' if PROFILE == 'isolated' else '14330'), DB_USER='sa', DB_PASSWORD=config['MSSQL_SA_PASSWORD'],
    DB_NAME='account_db', PAYMENT_DB_NAME='payment_db', TUITION_DB_NAME='tuition_db',
    DB_DRIVER='ODBC Driver 18 for SQL Server', DB_TRUST_SERVER_CERTIFICATE='yes')
for name in ('ACCOUNT_DATABASE_URL', 'PAYMENT_DATABASE_URL', 'TUITION_DATABASE_URL'):
    os.environ.pop(name, None)

from pwdlib import PasswordHash
from sqlalchemy import func, select, text

from services.account.database import SessionLocal as AccountSession
from services.account.models import Account, AccountEntry, User
from services.payment.database import SessionLocal as PaymentSession
from services.payment.models.payment import PaymentTransaction
from services.tuition.database import SessionLocal as TuitionSession
from services.tuition.models import Student, TuitionInvoice
from shared.time import utcnow

INTERNAL = {'X-Internal-Key': config['INTERNAL_API_KEY']}
COMPOSE = ['docker', 'compose', '--env-file', str(ROOT / 'infra/env/docker.env')]
if PROFILE == 'isolated':
    project = os.environ['IBANKING_TEST_PROJECT']
    if not re.fullmatch(r'ibanking-acceptance-[0-9a-f]{8}', project):
        raise RuntimeError('Invalid isolated project name')
    COMPOSE += ['-p', project, '-f', str(ROOT / 'compose.yaml'), '-f', str(ROOT / 'infra/docker/compose.acceptance.yaml')]
report = []


def request(service, method, path, *, headers=None, body=None):
    with httpx.Client(timeout=30, trust_env=False) as client:
        return client.request(method, f'http://127.0.0.1:{PORTS[service]}{path}', headers=headers, json=body)


def check(response, statuses=(200,)):
    assert response.status_code in statuses, (response.status_code, response.text)
    return response.json()


def new_user():
    suffix = uuid4().hex[:20]
    username, password = 'IT_' + suffix, 'IT_A1!' + uuid4().hex
    with AccountSession.begin() as db:
        user = User(username=username, password_hash=PasswordHash.recommended().hash(password),
            full_name='Integration Test', email=suffix + '@example.test', is_active=True)
        db.add(user)
        db.flush()
        account = Account(user_id=user.id, account_number='IT' + suffix,
            balance=Decimal('10000000.00'), status='ACTIVE')
        db.add(account)
        db.flush()
        result = {'user_id': user.id, 'account_id': account.id, 'username': username, 'password': password,
            'email': suffix + '@example.test'}
    token = check(request('account', 'POST', '/auth/login', body={'username': username, 'password': password}))['access_token']
    result['headers'] = {'Authorization': 'Bearer ' + token}
    return result


def new_student(amounts):
    with TuitionSession.begin() as db:
        student = Student(mssv='IT' + uuid4().hex[:20], full_name='Integration Student')
        db.add(student)
        db.flush()
        rows = [TuitionInvoice(student_id=student.id, semester='IT-HK' + str(index), amount_due=Decimal(amount))
            for index, amount in enumerate(amounts, start=1)]
        db.add_all(rows)
        db.flush()
        return student.mssv, [row.id for row in rows]


def create(user, mssv, ids=None):
    body = {'mssv': mssv, 'selection_mode': 'ALL_UNPAID' if ids is None else 'SELECTED'}
    if ids is not None:
        body['invoice_ids'] = ids
    return check(request('payment', 'POST', '/api/v1/payments',
        headers={**user['headers'], 'Idempotency-Key': str(uuid4())}, body=body), (201,))


def verify(user, payment):
    key = payment['payment_id']
    challenge = check(request('payment', 'POST', f'/api/v1/payments/{key}/send-otp', headers=user['headers']), (202,))
    from tests.integration.mailpit import message_for
    message = message_for(key)
    assert message['To'][0]['Address'] == user['email']
    codes = re.findall(r'Mã OTP của bạn:\s*(\d{6})', message['Text'])
    assert codes, 'Expected an SMTP OTP message'
    check(request('payment', 'POST', f'/api/v1/payments/{key}/verify-otp', headers=user['headers'],
        body={'challenge_id': challenge['challenge_id'], 'otp': codes[-1]}))


def process(user, payment):
    return request('payment', 'POST', '/api/v1/payments/' + payment['payment_id'] + '/process', headers=user['headers'])


def terminal(user, payment):
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            response = request('payment', 'GET', '/api/v1/payments/' + payment['payment_id'], headers=user['headers'])
            if response.status_code == 200:
                result = response.json()
                if result['status'] in {'SUCCEEDED', 'FAILED', 'REFUNDED'}:
                    return result
        except httpx.HTTPError:
            pass
        time.sleep(.5)
    raise AssertionError('Payment did not converge: ' + payment['payment_id'])


def parallel(jobs):
    barrier = Barrier(len(jobs))
    def worker(job):
        barrier.wait(timeout=10)
        return job()
    with ThreadPoolExecutor(max_workers=len(jobs)) as executor:
        return list(executor.map(worker, jobs))


def state(user):
    with AccountSession() as db:
        entries = db.scalars(select(AccountEntry).where(AccountEntry.account_id == user['account_id'])).all()
        return db.get(Account, user['account_id']).balance, [(row.payment_id, row.entry_type, row.amount) for row in entries]


def record(name):
    print('PASS:', name, flush=True)
    report.append({'name': name, 'result': 'PASS'})


def normal_and_ownership():
    user, other = new_user(), new_user()
    mssv, ids = new_student(['2000000.00', '3000000.00'])
    assert request('payment', 'GET', '/api/v1/payments').status_code == 401
    payment = create(user, mssv, [ids[0]])
    assert Decimal(payment['total_amount']) == Decimal('2000000.00')
    assert request('payment', 'GET', '/api/v1/payments/' + payment['payment_id'], headers=other['headers']).status_code == 404
    verify(user, payment)
    assert check(process(user, payment))['status'] == 'SUCCEEDED'
    assert check(process(user, payment))['status'] == 'SUCCEEDED'
    assert state(user)[0] == Decimal('8000000.00') and len(state(user)[1]) == 1
    remaining = create(user, mssv)
    assert [item['invoice_id'] for item in remaining['items']] == [ids[1]]
    verify(user, remaining)
    assert check(process(user, remaining))['status'] == 'SUCCEEDED'
    assert state(user)[0] == Decimal('5000000.00')
    record('JWT/ownership, selected invoice, ALL_UNPAID, repeat process')


def competing_balance():
    user = new_user()
    first = new_student(['7000000.00'])
    second = new_student(['7000000.00'])
    payments = [create(user, first[0]), create(user, second[0])]
    for payment in payments:
        verify(user, payment)
    responses = parallel([lambda payment=payment: process(user, payment) for payment in payments])
    for response in responses:
        check(response, (200, 202, 409))
    assert sorted(terminal(user, payment)['status'] for payment in payments) == ['FAILED', 'SUCCEEDED']
    balance, entries = state(user)
    assert balance == Decimal('3000000.00') and len(entries) == 1
    record('One account: concurrent 7M + 7M from 10M leaves exactly 3M')


def competing_invoices(overlap):
    users = [new_user(), new_user()]
    mssv, ids = new_student(['2000000.00', '3000000.00', '4000000.00'])
    selections = [ids[:2], ids[1:]] if overlap else [[ids[0]], [ids[0]]]
    payments = [create(user, mssv, selected) for user, selected in zip(users, selections)]
    for user, payment in zip(users, payments):
        verify(user, payment)
    responses = parallel([lambda user=user, payment=payment: process(user, payment) for user, payment in zip(users, payments)])
    for response in responses:
        check(response, (200, 202, 409))
    results = [terminal(user, payment) for user, payment in zip(users, payments)]
    assert sorted(result['status'] for result in results) == ['FAILED', 'SUCCEEDED']
    winner = next(index for index, result in enumerate(results) if result['status'] == 'SUCCEEDED')
    loser = 1 - winner
    assert len(state(users[winner])[1]) == 1
    assert state(users[loser]) == (Decimal('10000000.00'), [])
    with TuitionSession() as db:
        for invoice_id in ids:
            invoice = db.get(TuitionInvoice, invoice_id)
            assert invoice.status == ('PAID' if invoice_id in selections[winner] else 'UNPAID')
            if invoice.status == 'PAID':
                assert invoice.paid_payment_id == payments[winner]['payment_id']
    record('Overlapping invoice groups are all-or-nothing' if overlap else 'Two payers: same invoice is paid exactly once')


def duplicate_requests():
    user = new_user()
    mssv, ids = new_student(['2000000.00', '3000000.00'])
    payment = create(user, mssv)
    verify(user, payment)
    responses = parallel([lambda: process(user, payment) for _ in range(5)])
    for response in responses:
        check(response, (200, 202))
    assert terminal(user, payment)['status'] == 'SUCCEEDED'
    assert state(user)[0] == Decimal('5000000.00') and len(state(user)[1]) == 1
    record('Five concurrent process requests debit and finalize once')


def cancellation_fences():
    user = new_user()
    key = str(uuid4())
    body = {'payment_id': key, 'account_id': user['account_id'], 'payer_user_id': user['user_id'], 'amount': '1000000.00'}
    assert check(request('account', 'POST', '/internal/accounts/cancel', headers=INTERNAL, body=body))['status'] == 'CANCELLED'
    assert check(request('account', 'POST', '/internal/accounts/debit', headers=INTERNAL, body=body))['status'] == 'CANCELLED'
    mssv, ids = new_student(['1000000.00'])
    check(request('tuition', 'POST', f'/internal/tuition/reservations/{key}/release', headers=INTERNAL))
    reserve = {'payment_id': key, 'mssv': mssv, 'items': [{'invoice_id': ids[0], 'version': 1}], 'expected_total': '1000000.00'}
    assert request('tuition', 'POST', '/internal/tuition/reservations', headers=INTERNAL, body=reserve).status_code == 409
    assert state(user) == (Decimal('10000000.00'), [])
    record('Cancellation fences late debit and late reservation')


def restart_recovery():
    pending = []
    for phase in ('RESERVE', 'DEBIT', 'FINALIZE'):
        user = new_user()
        mssv, ids = new_student(['1000000.00', '2000000.00'])
        payment = create(user, mssv)
        verify(user, payment)
        key = payment['payment_id']
        reservation = {'payment_id': key, 'mssv': mssv,
            'items': [{'invoice_id': item['invoice_id'], 'version': item['invoice_version']} for item in payment['items']],
            'expected_total': payment['total_amount']}
        check(request('tuition', 'POST', '/internal/tuition/reservations', headers=INTERNAL, body=reservation))
        if phase in ('DEBIT', 'FINALIZE'):
            check(request('account', 'POST', '/internal/accounts/debit', headers=INTERNAL, body={
                'payment_id': key, 'account_id': user['account_id'], 'payer_user_id': user['user_id'], 'amount': payment['total_amount']}))
        if phase == 'FINALIZE':
            check(request('tuition', 'POST', f'/internal/tuition/reservations/{key}/finalize', headers=INTERNAL))
        pending.append((user, payment, phase))
    # Materialize states representing a crash after remote commit but before local commit.
    with PaymentSession.begin() as db:
        for user, payment, phase in pending:
            row = db.get(PaymentTransaction, payment['payment_id'])
            row.status, row.phase, row.next_retry_at = 'PROCESSING', phase, utcnow()
    subprocess.run(COMPOSE + ['restart', 'payment'], cwd=ROOT, capture_output=True, check=True)
    for user, payment, phase in pending:
        assert terminal(user, payment)['status'] == 'SUCCEEDED'
        assert state(user)[0] == Decimal('7000000.00') and len(state(user)[1]) == 1
    record('Restart recovery from persisted RESERVE / DEBIT / FINALIZE intent')


def smtp_outage_and_receipt_retry():
    from services.payment.models.payment import EmailOutbox
    from tests.integration.mailpit import message_for
    user = new_user()
    mssv, ids = new_student(['2000000.00'])
    payment = create(user, mssv)
    key = payment['payment_id']
    try:
        subprocess.run(COMPOSE + ['stop', 'mailpit'], cwd=ROOT, capture_output=True, check=True)
        assert request('payment', 'POST', f'/api/v1/payments/{key}/send-otp', headers=user['headers']).status_code == 503
    finally:
        subprocess.run(COMPOSE + ['start', 'mailpit'], cwd=ROOT, capture_output=True, check=True)
    verify(user, payment)
    try:
        subprocess.run(COMPOSE + ['stop', 'mailpit'], cwd=ROOT, capture_output=True, check=True)
        result = check(process(user, payment))
        assert result['status'] == 'SUCCEEDED' and result['receipt_status'] == 'PENDING'
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            with PaymentSession() as db:
                event = db.scalar(select(EmailOutbox).where(EmailOutbox.payment_id == key))
                if event.attempts > 0:
                    assert event.status == 'PENDING'
                    break
            time.sleep(.25)
        else:
            raise AssertionError('Receipt retry was not persisted')
        subprocess.run(COMPOSE + ['restart', 'payment'], cwd=ROOT, capture_output=True, check=True)
    finally:
        subprocess.run(COMPOSE + ['start', 'mailpit'], cwd=ROOT, capture_output=True, check=True)
    receipt = message_for(key, receipt=True, timeout=60)
    assert receipt['To'][0]['Address'] == user['email']
    assert mssv in receipt['Text'] and '2.000.000,00' in receipt['Text'] and 'THÀNH CÔNG' in receipt['Text']
    assert terminal(user, payment)['status'] == 'SUCCEEDED'
    assert check(process(user, payment))['status'] == 'SUCCEEDED'
    assert state(user)[0] == Decimal('8000000.00') and len(state(user)[1]) == 1
    with PaymentSession() as db:
        events = db.scalars(select(EmailOutbox).where(EmailOutbox.payment_id == key)).all()
        assert len(events) == 1 and events[0].status == 'SENT'
    record('SMTP outage/restart: OTP retry and receipt outbox do not repeat debiting')


def main():
    for service in ('account', 'payment', 'tuition'):
        check(request(service, 'GET', '/health/db'))
    for scenario in (normal_and_ownership, competing_balance, lambda: competing_invoices(False),
            lambda: competing_invoices(True), duplicate_requests, cancellation_fences, restart_recovery, smtp_outage_and_receipt_retry):
        scenario()
    target = ROOT / 'artifacts/backend-acceptance.json'
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps({'checked_at_utc': utcnow().isoformat() + 'Z', 'database': 'Docker localhost:14330',
        'checks': report}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'PASS: {len(report)} SQL Server acceptance scenarios; report: artifacts/backend-acceptance.json')


if __name__ == '__main__':
    main()
