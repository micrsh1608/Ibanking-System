"""Synthetic setup and read-only audit for real browser payment actions only."""
import base64
import json
import os
import re
import sys
from uuid import UUID

# Check before importing backend_acceptance: that module selects a SQL target.
if os.getenv('IBANKING_TEST_PROFILE') != 'isolated':
    raise RuntimeError('Web consistency fixtures require the isolated acceptance profile')

# These settings belong only to this fixture process, never the demo services.
os.environ.update(SMTP_HOST='mailpit', SMTP_PORT='1025', SMTP_USERNAME='', SMTP_PASSWORD='',
    SMTP_STARTTLS='false', SMTP_SSL='false', MAILPIT_SMTP_HOST='mailpit')

from sqlalchemy import select

from tests.integration import backend_acceptance as a
from tests.integration.mailpit import message_for
from services.payment.models.payment import EmailOutbox
from services.tuition.models import Reservation


def actor(user, mssv):
    return {key: user[key] for key in ('user_id', 'account_id', 'username', 'password', 'email')} | {'mssv': mssv}


def prepare(case):
    if case not in {'balance', 'tuition'}:
        raise ValueError('Unknown Web consistency case')
    config = a.check(a.request('account', 'GET', '/app-config'))
    if config.get('email_delivery') != 'mailpit':
        raise RuntimeError('Synthetic browser payments require the isolated Mailpit transport')
    users = [a.new_user() for _ in range(1 if case == 'balance' else 2)]
    with a.AccountSession.begin() as db:
        for user in users:
            db.get(a.User, user['user_id']).email_channel = 'mailpit'
    amounts = [['7000000.00'], ['7000000.00']] if case == 'balance' else [['2000000.00', '3000000.00']]
    students = []
    for group in amounts:
        mssv, ids = a.new_student(group)
        students.append({'mssv': mssv, 'invoice_ids': ids, 'amounts': group})
    actors = [actor(users[0], students[0]['mssv']),
        actor(users[-1], students[-1]['mssv'])]
    return {'case': case, 'actors': actors, 'students': students}


def read_otp(payment_id):
    key = str(UUID(payment_id))
    with a.PaymentSession() as db:
        payment = db.get(a.PaymentTransaction, key)
        if payment is None or not payment.mssv.startswith('IT') or payment.email_channel != 'mailpit':
            raise ValueError('OTP lookup accepts only synthetic Mailpit payments')
        user_id = payment.payer_user_id
    with a.AccountSession() as db:
        if not db.get(a.User, user_id).username.startswith('IT_'):
            raise ValueError('OTP lookup accepts only synthetic test users')
    message = message_for(key)
    match = re.search(r'Mã OTP của bạn:\s*(\d{6})', message['Text'])
    if not match:
        raise AssertionError('Synthetic payment OTP was not present')
    return {'otp': match.group(1)}


def decode_state(value):
    if len(value) > 65536:
        raise ValueError('Fixture state is too large')
    if not value.lstrip().startswith('{'):
        value = base64.b64decode(value, validate=True).decode('utf-8')
    state = json.loads(value)
    if state.get('case') not in {'balance', 'tuition'} or len(state.get('actors', [])) != 2:
        raise ValueError('Unknown synthetic audit state')
    if len(state.get('payment_ids', [])) != 2 or len(set(state['payment_ids'])) != 2:
        raise ValueError('Audit requires two independent browser payment UUIDs')
    state['payment_ids'] = [str(UUID(key)) for key in state['payment_ids']]
    return state


def audit(state):
    actors, keys = state['actors'], state['payment_ids']
    user_ids, account_ids = {int(row['user_id']) for row in actors}, {int(row['account_id']) for row in actors}
    with a.AccountSession() as db:
        for row in actors:
            user, account = db.get(a.User, int(row['user_id'])), db.get(a.Account, int(row['account_id']))
            if user is None or not user.username.startswith('IT_') or user.username != row['username'] or account.user_id != user.id:
                raise ValueError('Audit accepts only the synthetic users in its fixture state')
        accounts = [{'account_id': key, 'balance': format(db.get(a.Account, key).balance, '.2f')}
            for key in sorted(account_ids)]
        entries = [{'payment_id': row.payment_id, 'account_id': row.account_id,
            'entry_type': row.entry_type, 'amount': format(row.amount, '.2f')}
            for row in db.scalars(select(a.AccountEntry).where(a.AccountEntry.account_id.in_(account_ids)))]
    with a.PaymentSession() as db:
        payments = [{'payment_id': row.payment_id, 'payer_user_id': row.payer_user_id,
            'account_id': row.account_id, 'mssv': row.mssv, 'status': row.status, 'phase': row.phase,
            'total_amount': format(row.total_amount, '.2f'), 'email_channel': row.email_channel}
            for row in db.scalars(select(a.PaymentTransaction).where(a.PaymentTransaction.payer_user_id.in_(user_ids)))]
        events = [{'payment_id': row.payment_id, 'recipient': row.recipient, 'email_channel': row.email_channel}
            for row in db.scalars(select(EmailOutbox).where(EmailOutbox.payment_id.in_(keys)))]
    students, reservations = [], []
    with a.TuitionSession() as db:
        for expected in state['students']:
            mssv = expected['mssv']
            if not re.fullmatch(r'IT[0-9a-f]{20}', mssv):
                raise ValueError('Audit accepts only synthetic students')
            student = db.scalar(select(a.Student).where(a.Student.mssv == mssv))
            rows = list(db.scalars(select(a.TuitionInvoice).where(a.TuitionInvoice.student_id == student.id)
                .order_by(a.TuitionInvoice.id)))
            students.append({'mssv': mssv, 'invoices': [{'id': row.id, 'status': row.status,
                'amount': format(row.amount_due, '.2f'), 'paid_payment_id': row.paid_payment_id,
                'reserved_payment_id': row.reserved_payment_id} for row in rows]})
        reservations = [{'payment_id': row.payment_id, 'status': row.status}
            for row in db.scalars(select(Reservation).where(Reservation.payment_id.in_(keys)))]

    successes = [row for row in payments if row['status'] == 'SUCCEEDED']
    failures = [row for row in payments if row['status'] == 'FAILED']
    checks = {'exactly_two_browser_payments': {row['payment_id'] for row in payments} == set(keys),
        'one_success_one_failure': len(successes) == len(failures) == 1,
        'only_one_debit_no_refund': len(entries) == 1 and entries[0]['entry_type'] == 'DEBIT',
        'browser_ownership_and_snapshot': all(any(payment['payment_id'] == key and
            payment['payer_user_id'] == actor['user_id'] and payment['account_id'] == actor['account_id'] and
            payment['mssv'] == actor['mssv'] and payment['email_channel'] == 'mailpit' for payment in payments)
            for actor, key in zip(actors, keys)),
        'all_payments_terminal': all(row['phase'] == 'DONE' for row in payments)}
    if len(successes) == len(failures) == 1:
        winner = successes[0]
        amount = '7000000.00' if state['case'] == 'balance' else '5000000.00'
        checks['snapshot_totals'] = all(row['total_amount'] == amount for row in payments)
        checks['ledger_matches_winner'] = len(entries) == 1 and entries[0] == {
            'payment_id': winner['payment_id'], 'account_id': winner['account_id'], 'entry_type': 'DEBIT', 'amount': amount}
        checks['exact_balances'] = all(row['balance'] == (
            '3000000.00' if state['case'] == 'balance' else
            '5000000.00' if row['account_id'] == winner['account_id'] else '10000000.00') for row in accounts)
        checks['whole_invoice_groups'] = all(
            [row['id'] for row in student['invoices']] == expected['invoice_ids'] and
            [row['amount'] for row in student['invoices']] == expected['amounts'] and
            all(row['status'] == ('PAID' if student['mssv'] == winner['mssv'] else 'UNPAID') and
                row['paid_payment_id'] == (winner['payment_id'] if student['mssv'] == winner['mssv'] else None) and
                (student['mssv'] == winner['mssv'] or row['reserved_payment_id'] is None)
                for row in student['invoices'])
            for student, expected in zip(students, state['students']))
        checks['one_receipt_with_frozen_route'] = len(events) == 1 and events[0] == {
            'payment_id': winner['payment_id'], 'recipient': next(actor['email'] for actor in actors
                if actor['user_id'] == winner['payer_user_id']), 'email_channel': 'mailpit'}
        checks['reservations_converged'] = any(row == {'payment_id': winner['payment_id'], 'status': 'PAID'}
            for row in reservations) and all(row['status'] == ('PAID' if row['payment_id'] == winner['payment_id'] else 'RELEASED')
                for row in reservations)
    return {'case': state['case'], 'consistent': all(checks.values()), 'checks': checks,
        'accounts': accounts, 'entries': entries, 'payments': payments, 'students': students,
        'reservations': reservations, 'receipt_events': events}


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else ''
    if action == 'prepare':
        result = prepare(sys.argv[2])
    elif action == 'otp':
        result = read_otp(sys.argv[2])
    elif action == 'audit':
        result = audit(decode_state(sys.argv[2] if len(sys.argv) > 2 else sys.stdin.read()))
    else:
        raise ValueError('Use prepare CASE, otp UUID, or audit [JSON/base64]')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
