"""Isolated load/fault/clean-install acceptance. Never controls the user's demo project."""
import argparse
import hashlib
import json
import os
import statistics
import sys
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import httpx
from sqlalchemy import func, select, text

RUN_ID = uuid4().hex[:8]
PROJECT = 'ibanking-acceptance-' + RUN_ID
os.environ.update(IBANKING_TEST_PROFILE='isolated', IBANKING_TEST_PROJECT=PROJECT,
    IBANKING_TEST_IMAGE='ibanking-acceptance-api:' + RUN_ID)

from tests.integration import backend_acceptance as a
from tests.integration.mailpit import message_for
from services.account.models import Account, AccountEntry
from services.payment.models.payment import EmailOutbox, PaymentTransaction
from services.tuition.models import Student, TuitionInvoice, Reservation, ReservationItem

ROOT = a.ROOT
OUTPUT = ROOT / 'artifacts/release' / RUN_ID
OUTPUT.mkdir(parents=True, exist_ok=True)
report = {'run_id': RUN_ID, 'project': PROJECT, 'started_at_utc': a.utcnow().isoformat() + 'Z',
    'sql_server': '127.0.0.1,14331', 'checks': [], 'status': 'RUNNING'}


def command(args, *, name=None, check=True):
    result = subprocess.run(a.COMPOSE + args, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if name:
        output = result.stdout + '\n' + result.stderr
        for secret in a.config.values():
            if secret and len(secret) > 10:
                output = output.replace(secret, '[REDACTED]')
        (OUTPUT / (name + '.log')).write_text(output, encoding='utf-8')
    if check and result.returncode:
        raise RuntimeError('Acceptance Docker command failed: ' + ' '.join(args[:2]) + '; see ' + str(OUTPUT))
    return result.stdout


def wait_for(predicate, timeout=120):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        try:
            result = predicate()
            if result:
                return result
        except (httpx.HTTPError, OSError):
            pass
        time.sleep(.5)
    raise AssertionError('Acceptance condition did not become true within timeout')


def healthy():
    return all(a.request(service, 'GET', '/health/db').status_code == 200 for service in a.PORTS)


def check(name, details):
    report['checks'].append({'name': name, 'result': 'PASS', 'details': details})
    save()
    print('PASS:', name, flush=True)


def save():
    (OUTPUT / 'acceptance.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


def control(service, rule=None):
    port = 9101 if service == 'account' else 9102
    with httpx.Client(timeout=5, trust_env=False) as client:
        if rule:
            result = client.post(f'http://127.0.0.1:{port}/__faults', json=rule)
        else:
            result = client.delete(f'http://127.0.0.1:{port}/__faults')
        result.raise_for_status()


def proxy_events(service):
    port = 9101 if service == 'account' else 9102
    with httpx.Client(timeout=5, trust_env=False) as client:
        return client.get(f'http://127.0.0.1:{port}/__faults').json()['events']


def settle(user, payment, timeout=120):
    def done():
        response = a.request('payment', 'GET', '/api/v1/payments/' + payment['payment_id'], headers=user['headers'])
        if response.status_code == 200 and response.json()['status'] in {'SUCCEEDED', 'FAILED', 'REFUNDED'}:
            return response.json()
    return wait_for(done, timeout)


def audit(user, payment, amount):
    key = payment['payment_id']
    with a.AccountSession() as db:
        account = db.get(Account, user['account_id'])
        entries = db.scalars(select(AccountEntry).where(AccountEntry.payment_id == key)).all()
        assert len(entries) == 1 and entries[0].entry_type == 'DEBIT' and entries[0].amount == amount
    with a.TuitionSession() as db:
        rows = [db.get(TuitionInvoice, item['invoice_id']) for item in payment['items']]
        assert all(row.status == 'PAID' and row.paid_payment_id == key for row in rows)
        assert sum((row.amount_due for row in rows), Decimal('0')) == amount
    with a.PaymentSession() as db:
        record = db.get(PaymentTransaction, key)
        assert record.status == 'SUCCEEDED' and record.total_amount == amount
        assert db.scalar(select(func.count()).select_from(EmailOutbox).where(EmailOutbox.payment_id == key)) == 1
    return {'payment_id': key, 'invoice_count': len(rows), 'amount': str(amount), 'debits': 1,
        'balance': str(account.balance), 'status': 'SUCCEEDED'}


def prepared(amount='1000000.00'):
    user = a.new_user()
    mssv, _ = a.new_student([amount])
    payment = a.create(user, mssv)
    a.verify(user, payment)
    return user, payment


def clean_install():
    wait_for(healthy)
    with a.AccountSession() as db:
        assert db.scalar(select(func.count()).select_from(a.User)) == 1
        user = db.scalar(select(a.User).where(a.User.username == 'huy'))
        account = db.scalar(select(Account).where(Account.user_id == user.id))
        assert account.balance == Decimal('10000000.00')
        account_id = account.id
    with a.TuitionSession() as db:
        student = db.scalar(select(Student).where(Student.mssv == 'SV20261013'))
        invoices = db.scalars(select(TuitionInvoice).where(TuitionInvoice.student_id == student.id).order_by(TuitionInvoice.id)).all()
        assert len(invoices) == 2 and all(row.status == 'UNPAID' for row in invoices)
        ids = [row.id for row in invoices]
    with a.PaymentSession() as db:
        assert db.scalar(select(func.count()).select_from(PaymentTransaction)) == 0
    token = a.check(a.request('account', 'POST', '/auth/login', body={'username': 'huy', 'password': 'HuyDemo_123!'}))['access_token']
    actor = {'headers': {'Authorization': 'Bearer ' + token}, 'user_id': user.id,
        'account_id': account_id, 'email': user.email, 'password': 'HuyDemo_123!'}
    a.verify_email(actor)
    payments = []
    for mssv in ['SV20261013']:
        payment = a.create(actor, mssv)
        a.verify(actor, payment)
        assert a.check(a.process(actor, payment), (200, 202))['status'] in {'SUCCEEDED', 'PROCESSING', 'PENDING_RECONCILIATION'}
        assert settle(actor, payment)['status'] == 'SUCCEEDED'
        message_for(payment['payment_id'], receipt=True)
        payments.append(payment['payment_id'])
    command(['run', '--rm', 'db-init'], name='seed-repeat')
    with a.AccountSession() as db:
        assert db.get(Account, account_id).balance == Decimal('5000000.00')
        assert db.scalar(select(func.count()).select_from(a.User)) == 1
    with a.TuitionSession() as db:
        assert all(db.get(TuitionInvoice, key).status == 'PAID' for key in ids)
    check('Clean installation and 5-10 minute demo rehearsal', {'new_volumes': True,
        'all_unpaid_and_terms': True, 'otp_and_receipts_smtp': True,
        'seed_repeat_kept_balance_and_paid_status': True, 'payment_ids': payments})


def load(workers, count):
    actors = [a.new_user() for _ in range((count + 3) // 4)]
    jobs = []
    for index in range(count):
        user = actors[index // 4]
        mssv, _ = a.new_student(['500000.00', '500000.00'])
        payment = a.create(user, mssv)
        a.verify(user, payment)
        jobs.append((user, payment))
    latencies, responses = [], []
    def worker(job):
        started = time.perf_counter()
        try:
            response = a.process(*job)
            return response.status_code, time.perf_counter() - started
        except httpx.HTTPError:
            return 599, time.perf_counter() - started
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        values = list(executor.map(worker, jobs))
    for code, seconds in values:
        latencies.append(seconds)
        responses.append(code)
    # Retry same UUID only if admission failed before durable PROCESSING intent.
    for (user, payment), code in zip(jobs, responses):
        if code not in (200, 202):
            a.process(user, payment)
        assert settle(user, payment)['status'] == 'SUCCEEDED'
    elapsed = time.perf_counter() - started
    records = [audit(user, payment, Decimal('1000000.00')) for user, payment in jobs]
    for index, actor in enumerate(actors):
        paid = min(4, count - index * 4)
        assert a.state(actor)[0] == Decimal('10000000.00') - Decimal(paid) * Decimal('1000000.00')
    ordered = sorted(latencies)
    metrics = {'workers': workers, 'payments': count, 'invoices': count * 2,
        'response_codes': {str(code): responses.count(code) for code in sorted(set(responses))},
        'p50_seconds': round(statistics.median(ordered), 3),
        'p95_seconds': round(ordered[max(0, int(len(ordered) * .95) - 1)], 3),
        'max_seconds': round(max(ordered), 3), 'convergence_seconds': round(elapsed, 3),
        'completed_per_second': round(count / elapsed, 3), 'ledger_and_invoice_audit': records}
    report['load'] = metrics
    save()
    assert all(code in (200, 202) for code in responses), 'Load admission had errors; inspect load metrics'
    check('Concurrent payment load with exact three-database audit', metrics)


def lost_commit_reply(service):
    user, payment = prepared()
    key = payment['payment_id']
    path = '/internal/accounts/debit' if service == 'account' else f'/internal/tuition/reservations/{key}/finalize'
    control(service, {'path': path, 'mode': 'delay_after', 'seconds': 14, 'remaining': 1})
    try:
        result = a.check(a.process(user, payment), (200, 202))
        assert result['status'] in {'PENDING_RECONCILIATION', 'PROCESSING', 'SUCCEEDED'}
        assert settle(user, payment)['status'] == 'SUCCEEDED'
        assert any(event['path'] == path and event['upstream_status'] == 200 for event in proxy_events(service))
        detail = audit(user, payment, Decimal('1000000.00'))
        detail['delayed_reply_seconds'] = 14
        check('Lost committed ' + service + ' reply over real HTTP', detail)
    finally:
        control(service)


def network_partition():
    user, payment = prepared()
    target = command(['ps', '-q', 'tuition-faults']).strip()
    network = PROJECT + '_default'
    subprocess.run(['docker', 'network', 'disconnect', network, target], check=True, capture_output=True)
    try:
        result = a.check(a.process(user, payment), (202,))
        assert result['status'] == 'PENDING_RECONCILIATION'
        assert a.state(user) == (Decimal('10000000.00'), [])
    finally:
        subprocess.run(['docker', 'network', 'connect', '--alias', 'tuition-faults', network, target], check=True, capture_output=True)
    assert settle(user, payment)['status'] == 'SUCCEEDED'
    check('Docker network partition and recovery', audit(user, payment, Decimal('1000000.00')))


def payment_crash_after_debit():
    user, payment = prepared()
    path = '/internal/accounts/debit'
    control('account', {'path': path, 'mode': 'delay_after', 'seconds': 25, 'remaining': 1})
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(a.process, user, payment)
        try:
            wait_for(lambda: any(event['path'] == path and event['upstream_status'] == 200 for event in proxy_events('account')), 20)
            command(['kill', 'payment'], name='payment-kill')
        finally:
            command(['start', 'payment'], name='payment-start')
        try:
            future.result(timeout=35)
        except httpx.HTTPError:
            pass
    assert settle(user, payment)['status'] == 'SUCCEEDED'
    control('account')
    check('SIGKILL Payment after Account commit and before reply', audit(user, payment, Decimal('1000000.00')))


def sql_crash_in_transaction():
    from services.account.database import engine
    user, payment = prepared()
    uncommitted_id = str(uuid4())
    connection = engine.connect()
    transaction = connection.begin()
    try:
        connection.execute(text('UPDATE accounts SET balance=balance-1000000 WHERE id=:id'), {'id': user['account_id']})
        connection.execute(text("INSERT INTO account_entries(payment_id,account_id,entry_type,amount) VALUES(:key,:id,'DEBIT',1000000)"),
            {'key': uncommitted_id, 'id': user['account_id']})
        command(['kill', 'sqlserver'], name='sqlserver-kill')
        connection.invalidate()
        transaction.rollback()
        response = a.process(user, payment)
        assert response.status_code == 503
    finally:
        connection.close()
        command(['start', 'sqlserver'], name='sqlserver-start')
    wait_for(healthy, 120)
    with a.AccountSession() as db:
        assert db.get(Account, user['account_id']).balance == Decimal('10000000.00')
        assert db.scalar(select(func.count()).select_from(AccountEntry).where(AccountEntry.payment_id == uncommitted_id)) == 0
    assert a.check(a.process(user, payment), (200, 202))['status'] in {'SUCCEEDED', 'PROCESSING', 'PENDING_RECONCILIATION'}
    assert settle(user, payment)['status'] == 'SUCCEEDED'
    check('SQL Server SIGKILL rolls back an uncommitted balance and ledger',
        {**audit(user, payment, Decimal('1000000.00')), 'uncommitted_entry_count': 0})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cached-build', action='store_true')
    parser.add_argument('--full-checks', action='store_true', help='Also run SQL concurrency and browser acceptance in this isolated stack')
    parser.add_argument('--workers', type=int, default=16, choices=range(1, 33))
    parser.add_argument('--payments', type=int, default=32, choices=range(4, 65))
    args = parser.parse_args()
    report['clean_image_build'] = not args.cached_build
    try:
        print('Isolated acceptance project: ' + PROJECT, flush=True)
        command(['config', '--quiet'])
        command(['build'] + ([] if args.cached_build else ['--no-cache']) + ['db-init'], name='image-build')
        command(['up', '--no-build', '--wait', '--wait-timeout', '300'], name='clean-start')
        clean_install()
        if args.full_checks:
            result=subprocess.run([sys.executable,'-m','tests.integration.backend_acceptance'],cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace')
            (OUTPUT/'backend-checks.log').write_text(result.stdout+'\n'+result.stderr,encoding='utf8')
            if result.returncode: raise RuntimeError('SQL backend acceptance failed; see backend-checks.log')
            report['backend_checks']='PASS'
            print('PASS: isolated SQL concurrency acceptance',flush=True)
            result=subprocess.run([sys.executable,'-m','tests.integration.otp_consistency_acceptance'],cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace')
            (OUTPUT/'otp-consistency-checks.log').write_text(result.stdout+'\n'+result.stderr,encoding='utf8')
            if result.returncode:raise RuntimeError('OTP/consistency acceptance failed; see otp-consistency-checks.log')
            report['otp_consistency_checks']='PASS'
            print('PASS: isolated OTP and successful-payment consistency acceptance',flush=True)
            result=subprocess.run([sys.executable,'-m','tests.integration.email_verification_acceptance'],cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace')
            (OUTPUT/'email-verification-checks.log').write_text(result.stdout+'\n'+result.stderr,encoding='utf8')
            if result.returncode:raise RuntimeError('Email verification acceptance failed; see email-verification-checks.log')
            report['email_verification_checks']='PASS'
            print('PASS: isolated email ownership verification acceptance',flush=True)
            result=subprocess.run([sys.executable,'-m','tests.integration.observability_acceptance'],cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace')
            (OUTPUT/'observability-checks.log').write_text(result.stdout+'\n'+result.stderr,encoding='utf8')
            if result.returncode:raise RuntimeError('Observability acceptance failed; see observability-checks.log')
            report['observability_checks']='PASS'
            print('PASS: isolated gateway and three-service request tracing',flush=True)
        load(args.workers, args.payments)
        lost_commit_reply('account')
        lost_commit_reply('tuition')
        network_partition()
        payment_crash_after_debit()
        sql_crash_in_transaction()
        wait_for(healthy)
        if args.full_checks:
            browser_env=os.environ.copy(); browser_env['IBANKING_E2E_BASE_URL']='http://127.0.0.1:8101'
            result=subprocess.run(['npm.cmd' if os.name=='nt' else 'npm','run','test:e2e'],cwd=ROOT,env=browser_env,capture_output=True,text=True,encoding='utf8',errors='replace')
            (OUTPUT/'browser-checks.log').write_text(result.stdout+'\n'+result.stderr,encoding='utf8')
            if result.returncode: raise RuntimeError('Browser acceptance failed; see browser-checks.log')
            report['browser_checks']='PASS'
            print('PASS: isolated browser acceptance',flush=True)
        report['status'] = 'PASS'
        report['image_id'] = subprocess.run(['docker', 'image', 'inspect', '--format', '{{.Id}}', os.environ['IBANKING_TEST_IMAGE']], capture_output=True, text=True, check=True).stdout.strip()
    except Exception as error:
        report['status'], report['error_type'], report['error'] = 'FAIL', type(error).__name__, str(error)[:800]
        command(['logs', '--tail', '80', 'account', 'tuition', 'payment', 'db-init'], name='failure', check=False)
        raise
    finally:
        report['finished_at_utc'] = a.utcnow().isoformat() + 'Z'
        report['volumes_retained'] = [PROJECT + '_sqlserver-data', PROJECT + '_mailpit-data']
        command(['down', '--timeout', '20'], name='teardown', check=False)
        save()
        (ROOT / 'artifacts/release-acceptance-latest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('PASS: isolated release acceptance; report: ' + str(OUTPUT / 'acceptance.json'), flush=True)


if __name__ == '__main__':
    main()
