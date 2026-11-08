"""Stable SMTP-only demo provisioning tests: SQLite only, no real email."""
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from infra.docker import demo_catalog as catalog
from services.account import seed as account_seed
from services.account.database import Base as AccountBase
from services.account.models import Account, User
from services.tuition.database import Base as TuitionBase
from services.tuition.models import Student, TuitionInvoice


def environment():
    return {'IBANKING_DEMO_CATALOG_TARGET': 'ibanking-demo',
            'DB_SERVER': 'sqlserver,1433', 'DB_NAME': 'account_db',
            'PAYMENT_DB_NAME': 'payment_db', 'TUITION_DB_NAME': 'tuition_db',
            'SMTP_USERNAME': 'owner@example.org', 'SMTP_FROM': 'iBanking <sender@example.org>'}


@pytest.fixture
def databases(monkeypatch):
    engines = [create_engine('sqlite+pysqlite:///:memory:') for _ in range(2)]
    AccountBase.metadata.create_all(engines[0])
    TuitionBase.metadata.create_all(engines[1])
    sessions = [sessionmaker(bind=engine) for engine in engines]
    monkeypatch.setattr(account_seed, 'password_hasher', SimpleNamespace(hash=lambda _: 'test-hash-for-new-demo-users'))
    yield SimpleNamespace(account=sessions[0], tuition=sessions[1])
    for engine in engines:
        engine.dispose()


@pytest.mark.parametrize('change', [
    {'IBANKING_DEMO_CATALOG_TARGET': 'ibanking-consistency-demo'},
    {'DB_SERVER': 'HUY-PC'}, {'DB_SERVER': '127.0.0.1,14330'},
    {'DB_NAME': 'master'}, {'TUITION_DB_NAME': 'production'},
    {'ACCOUNT_DATABASE_URL': 'sqlite://'}, {'PAYMENT_DATABASE_URL': 'sqlite://'},
    {'TUITION_DATABASE_URL': 'sqlite://'},
])
def test_catalog_refuses_unknown_targets_before_opening_any_session(change):
    class NoConnection:
        def begin(self):
            pytest.fail('Environment guard must run before opening a database')
    with pytest.raises(catalog.CatalogError):
        catalog.provision(NoConnection(), NoConnection(), environ=environment() | change)


def test_catalog_never_uses_smtp_login_or_sender_as_a_user_recipient():
    plan = account_seed.demo_account_plan({'SMTP_USERNAME': 'owner@example.org', 'SMTP_FROM': 'sender@example.org'})
    assert len(plan) == 10
    assert all(user['email'] == '' and user['email_channel'] == 'smtp' for user in plan)


def test_provisioning_does_not_require_or_send_to_smtp_credentials(databases):
    result = catalog.provision(databases.account, databases.tuition,
        environ=environment() | {'SMTP_USERNAME': 'bad', 'SMTP_FROM': 'invalid'})
    assert result['manual_verification_required'] == 10
    assert all(user['verification'] == 'manual_on_profile' for user in result['users'])


def test_new_catalog_creates_ten_unverified_users_and_keeps_huy_untouched(databases):
    with databases.account.begin() as db:
        huy = User(username='huy', password_hash='private-existing-hash', full_name='Existing Huy',
                   email='huy@example.org', phone='0900000001', is_active=True)
        db.add(huy); db.flush()
        db.add(Account(user_id=huy.id, account_number='ORIGINAL-HUY', balance=Decimal('6100000.00'), status='ACTIVE'))
    result = catalog.provision(databases.account, databases.tuition, environ=environment())
    assert [row['username'] for row in result['users']] == ['demo' + str(i).zfill(2) for i in range(1, 11)]
    assert all(row['created'] and not row['email_verified'] for row in result['users'])
    assert all(row['balance'] == '10000000.00' for row in result['users'])
    assert all(row['email'] == '' and row['email_channel'] == 'smtp' for row in result['users'])
    assert result['manual_verification_required'] == 10
    assert len(result['students']) == 12
    assert [row['mssv'] for row in result['students']] == [f'SV2026{number}' for number in range(1001, 1013)]
    assert [row['id'] for row in result['students']] == list(range(1, 13))
    assert [invoice['id'] for row in result['students'] for invoice in row['invoices']] == list(range(1, 14))
    assert all('demo' not in row['student_name'].lower() for row in result['students'])
    assert all(invoice['semester'].startswith('2026-2027-HK') for row in result['students'] for invoice in row['invoices'])
    extras = {row['mssv']: row for row in result['students'] if row['mssv'] in {'SV20261001', 'SV20261002'}}
    assert {key: row['unpaid_total'] for key, row in extras.items()} == {'SV20261001': '2500000.00', 'SV20261002': '3500000.00'}
    assert all(invoice['status'] == 'UNPAID' for row in extras.values() for invoice in row['invoices'])
    same = next(row for row in result['students'] if row['mssv'] == 'SV20261005')
    assert [row['amount'] for row in same['invoices']] == ['2000000.00', '3000000.00']
    with databases.account() as db:
        huy = db.scalar(select(User).where(User.username == 'huy'))
        assert huy.password_hash == 'private-existing-hash'
        assert db.scalar(select(Account.balance).where(Account.user_id == huy.id)) == Decimal('6100000.00')


def test_rerun_preserves_changed_password_profile_balance_and_paid_invoice(databases):
    catalog.provision(databases.account, databases.tuition, environ=environment())
    with databases.account.begin() as db:
        user = db.scalar(select(User).where(User.username == 'demo02'))
        user.password_hash = 'user-changed-password'
        user.email, user.full_name = 'new-owner@example.org', 'Changed profile'
        account = db.scalar(select(Account).where(Account.user_id == user.id))
        account.balance = Decimal('3000000.00')
    with databases.tuition.begin() as db:
        student = db.scalar(select(Student).where(Student.mssv == 'SV20261005'))
        invoice = db.scalar(select(TuitionInvoice).where(TuitionInvoice.student_id == student.id).order_by(TuitionInvoice.id))
        invoice.status, invoice.paid_payment_id, invoice.version = 'PAID', 'existing-payment', 3
        saved_invoice_id = invoice.id
    result = catalog.provision(databases.account, databases.tuition, environ=environment())
    assert not any(row['created'] for row in result['users'])
    with databases.account() as db:
        user = db.scalar(select(User).where(User.username == 'demo02'))
        assert (user.password_hash, user.email, user.full_name) == ('user-changed-password', 'new-owner@example.org', 'Changed profile')
        assert db.scalar(select(Account.balance).where(Account.user_id == user.id)) == Decimal('3000000.00')
        assert db.scalar(select(func.count()).select_from(User)) == 10
    with databases.tuition() as db:
        invoice = db.get(TuitionInvoice, saved_invoice_id)
        assert (invoice.status, invoice.paid_payment_id, invoice.version) == ('PAID', 'existing-payment', 3)
        assert db.scalar(select(func.count()).select_from(TuitionInvoice)) == 13


def test_existing_unknown_demo_username_is_never_claimed_by_the_catalog(databases):
    with databases.account.begin() as db:
        user = User(username='demo01', password_hash='original', full_name='Unrelated owner',
                    email='unrelated@example.org', is_active=True)
        db.add(user); db.flush()
        db.add(Account(user_id=user.id, account_number='NOT-A-CATALOG-ACCOUNT', balance=Decimal('456.00')))
    with pytest.raises(catalog.CatalogError):
        catalog.provision(databases.account, databases.tuition, environ=environment())
    with databases.account() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1
        assert db.scalar(select(Account.balance)) == Decimal('456.00')


def test_a_reserved_account_number_cannot_be_taken_from_an_existing_owner(databases):
    with databases.account.begin() as db:
        owner = User(username='another_owner', password_hash='original', full_name='Original owner',
                     email='another@example.org', is_active=True)
        db.add(owner); db.flush()
        db.add(Account(user_id=owner.id, account_number='DEMO10000001', balance=Decimal('789.00')))
    with pytest.raises(catalog.CatalogError):
        catalog.provision(databases.account, databases.tuition, environ=environment())
    with databases.account() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1
        assert db.scalar(select(Account.balance)) == Decimal('789.00')



def test_catalog_has_no_mailbox_reader_or_automatic_email_verifier():
    assert not hasattr(catalog, 'mailpit_code')
    assert not hasattr(catalog, 'verify_synthetic_users')
