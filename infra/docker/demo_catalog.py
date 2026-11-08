"""Provision a stable main-app demo catalog without resetting existing data.

Only new catalog users receive a starting balance/password. Each user enters
and verifies their real email on the profile screen. Provisioning never sends
email, confirms email ownership, or calls a payment or money endpoint.
"""
import json
import os

from services.account.seed import DEMO_PASSWORD as PASSWORD, DemoSeedError as CatalogError


def require_catalog_environment(environ=None):
    env = os.environ if environ is None else environ
    expected = {'IBANKING_DEMO_CATALOG_TARGET': 'ibanking-demo',
                'DB_SERVER': 'sqlserver,1433', 'DB_NAME': 'account_db',
                'PAYMENT_DB_NAME': 'payment_db', 'TUITION_DB_NAME': 'tuition_db'}
    if any(env.get(key) != value for key, value in expected.items()):
        raise CatalogError('Use start.ps1 -PrepareDemo against the main local Docker project only.')
    if any(env.get(key) for key in ('ACCOUNT_DATABASE_URL', 'PAYMENT_DATABASE_URL', 'TUITION_DATABASE_URL')):
        raise CatalogError('Custom database URL overrides are not allowed for the demo catalog.')


def provision(account_session=None, tuition_session=None, *, environ=None):
    require_catalog_environment(environ)
    # Each service owns its seed data. Provisioning never proves email ownership.
    from services.account.seed import seed_demo_accounts
    from services.tuition.seed import DemoTuitionSeedError, seed_demo_students
    users = seed_demo_accounts(account_session, environ=environ)
    for user in users:
        user['verification'] = 'already_verified' if user['email_verified'] else 'manual_on_profile'
    try:
        students = seed_demo_students(tuition_session)
    except DemoTuitionSeedError as error:
        raise CatalogError(str(error)) from None
    return {'status': 'PREPARED', 'default_password': PASSWORD, 'users': users, 'students': students,
            'manual_verification_required': sum(not user['email_verified'] for user in users),
            'cases': {'balance': {'users': ['demo02'], 'mssvs': ['SV20261003', 'SV20261004'],
                                  'initial_balance': '10000000.00', 'debt_each': '7000000.00', 'expected_balance': '3000000.00'},
                      'tuition': {'users': ['demo03', 'demo04'], 'mssvs': ['SV20261005'],
                                  'debt_total': '5000000.00', 'winner_balance': '5000000.00', 'loser_balance': '10000000.00'},
                      'smtp': {'users': ['demo01'], 'mssvs': ['SV20261006'], 'debt_total': '1000000.00'}},
            'note': 'Only newly created users receive the default password and 10M. Existing profiles, balances, passwords and paid invoices were preserved.'}


def main():
    require_catalog_environment()
    print(json.dumps(provision(), ensure_ascii=True, indent=2))


if __name__ == '__main__':
    try:
        main()
    except CatalogError as error:
        print(json.dumps({'status': 'ERROR', 'error': str(error)}, ensure_ascii=True))
        raise SystemExit(1)
    except Exception:
        # Driver errors may include connection details; do not expose them.
        print(json.dumps({'status': 'ERROR', 'error': 'Catalog preparation failed. Check service health and catalog ownership; existing data was not reset.'}))
        raise SystemExit(1)
