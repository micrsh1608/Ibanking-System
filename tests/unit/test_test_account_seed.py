"""Create one extra local payer without resetting another user's money/profile."""
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from services.account import seed
from services.account.database import Base
from services.account.models import Account, User


@pytest.fixture
def database(monkeypatch):
    engine = create_engine('sqlite+pysqlite:///:memory:')
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(seed, 'password_hasher', SimpleNamespace(hash=lambda password: 'hashed:' + password))
    yield sessions
    engine.dispose()


def test_second_payer_gets_a_separate_active_account_and_unverified_own_email(database):
    result = seed.create_test_account(email='second-user@example.org', session_factory=database)
    assert result['status'] == 'CREATED' and result['username'] == 'huy2'
    assert result['account_number'] == '1000000002' and result['balance'] == '10000000.00'
    assert result['email'] == 'second-user@example.org'
    assert result['email_channel'] == 'smtp' and result['email_verified'] is False
    assert result['initial_password'] == 'HuyDemo_123!'
    with database() as db:
        user = db.scalar(select(User))
        account = db.scalar(select(Account))
        assert user.password_hash == 'hashed:HuyDemo_123!'
        assert user.full_name == 'Nguyễn Minh Nam' and user.phone == '0900000002'
        assert user.email_verified_at is None and user.pending_email is None
        assert user.is_active and account.status == 'ACTIVE'
        assert account.user_id == user.id


def test_seed_can_leave_the_email_empty_for_entry_on_the_profile_screen(database):
    result = seed.create_test_account(session_factory=database)
    assert result['email'] == '' and result['email_verified'] is False


def test_rerun_preserves_changed_password_email_profile_verification_and_balance(database):
    seed.create_test_account(email='initial@example.org', session_factory=database)
    stamp = datetime(2026, 11, 7, 8)
    with database.begin() as db:
        user = db.scalar(select(User))
        user.password_hash = 'private-changed-hash'
        user.full_name, user.email = 'Changed Name', 'verified-owner@example.org'
        user.email_verified_at = stamp
        account = db.scalar(select(Account))
        account.balance, account.status = Decimal('3000000.00'), 'LOCKED'
    result = seed.create_test_account(email='other-candidate@example.org', session_factory=database)
    assert result['status'] == 'PRESERVED' and result['created'] is False
    assert result['initial_password'] is None and result['email'] == 'verified-owner@example.org'
    assert result['balance'] == '3000000.00' and result['account_status'] == 'LOCKED'
    with database() as db:
        user = db.scalar(select(User))
        assert (user.password_hash, user.full_name, user.email_verified_at) == ('private-changed-hash', 'Changed Name', stamp)
        assert db.scalar(select(func.count()).select_from(User)) == 1
        assert db.scalar(select(func.count()).select_from(Account)) == 1


@pytest.mark.parametrize('username,number', [('huy2', 'OTHER-NUMBER'), ('original_owner', '1000000002')])
def test_existing_username_or_account_number_cannot_be_taken(database, username, number):
    with database.begin() as db:
        user = User(username=username, full_name='Original Owner', password_hash='original',
            email='owner@example.org', is_active=True)
        db.add(user)
        db.flush()
        db.add(Account(user_id=user.id, account_number=number, balance=Decimal('765.00')))
    with pytest.raises(seed.DemoSeedError):
        seed.create_test_account(email='second@example.org', session_factory=database)
    with database() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1
        assert db.scalar(select(Account.balance)) == Decimal('765.00')


@pytest.mark.parametrize('values', [
    {'username': 'bad user'}, {'username': 'huy2; DROP TABLE users'}, {'username': 'HUY2'},
    {'email': 'bad'}, {'email': 'a@example.org\r\nBcc: victim@example.org'},
])
def test_bad_account_metadata_fails_before_opening_a_database(values):
    class NoConnection:
        def begin(self):
            pytest.fail('Must validate before opening a database')
    with pytest.raises(seed.DemoSeedError):
        seed.create_test_account(session_factory=NoConnection(), **values)
