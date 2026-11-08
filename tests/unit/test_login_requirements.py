from datetime import datetime, timedelta, timezone
import os

import jwt
import pytest

from services.account.database import SessionLocal
from services.account.models import User
from services.account.security import password_hasher
from tests.unit.conftest import token


PASSWORD = ' Login_123! '


@pytest.fixture
def credentials(stack):
    with SessionLocal.begin() as db:
        db.get(User, 1).password_hash = password_hasher.hash(PASSWORD)
    return {'username': 'user1', 'password': PASSWORD}


@pytest.mark.parametrize('username', ['user1', ' USER1 ', 'UsEr1'])
def test_login_normalizes_username_but_preserves_password(stack, credentials, username):
    response = stack.account.post('/auth/login', json=credentials | {'username': username})
    assert response.status_code == 200
    assert set(response.json()) == {'access_token', 'token_type'}
    assert response.json()['token_type'] == 'bearer'
    headers = {'Authorization': 'Bearer ' + response.json()['access_token']}
    user = stack.account.get('/users/me', headers=headers).json()
    account = stack.account.get('/accounts/me', headers=headers).json()
    assert user['id'] == 1 and user['phone'] == '0900000001'
    assert user['full_name'] == 'User 1' and user['email'] == 'user1@example.test'
    assert 'password_hash' not in user and 'password' not in user
    assert account['account_number'] == '1000000001' and account['balance'] == '10000000.00'


@pytest.mark.parametrize('change', [{'username': 'no_such_user'}, {'password': 'wrong'}, {'password': PASSWORD.strip()}])
def test_invalid_credentials_have_one_generic_error_and_no_token(stack, credentials, change):
    response = stack.account.post('/auth/login', json=credentials | change)
    assert response.status_code == 401
    assert response.json() == {'detail': 'Sai tên đăng nhập hoặc mật khẩu'}
    assert response.headers['www-authenticate'] == 'Bearer'


@pytest.mark.parametrize('stored_hash', ['old-unsupported-hash', '$argon2id$invalid'])
def test_unrecognized_stored_hash_denies_login_without_server_error(stack, credentials, stored_hash):
    with SessionLocal.begin() as db:
        db.get(User, 1).password_hash = stored_hash
    response = stack.account.post('/auth/login', json=credentials)
    assert response.status_code == 401
    assert response.json() == {'detail': 'Sai tên đăng nhập hoặc mật khẩu'}


def test_disabled_user_cannot_login_or_read_or_update_account_profile(stack, credentials):
    with SessionLocal.begin() as db:
        db.get(User, 1).is_active = False
    assert stack.account.post('/auth/login', json=credentials).status_code == 403
    for path in ('/users/me', '/accounts/me'):
        assert stack.account.get(path, headers=stack.headers).status_code == 403
    profile = {'full_name': 'Changed User', 'email': 'new@example.test', 'phone': '0900000001', 'current_password': PASSWORD}
    assert stack.account.put('/users/me', headers=stack.headers, json=profile).status_code == 403
    with SessionLocal() as db:
        assert db.get(User, 1).full_name == 'User 1'


@pytest.mark.parametrize('case', ['absent', 'malformed', 'expired', 'signature', 'issuer', 'audience', 'missing_exp', 'subject'])
def test_account_payment_and_tuition_reject_invalid_sessions(stack, case):
    now = datetime.now(timezone.utc)
    claims = {'sub': '1', 'iat': now, 'exp': now + timedelta(minutes=5), 'iss': 'account-service', 'aud': 'ibanking'}
    if case == 'expired': claims['exp'] = now - timedelta(seconds=1)
    if case == 'issuer': claims['iss'] = 'another-service'
    if case == 'audience': claims['aud'] = 'another-app'
    if case == 'missing_exp': claims.pop('exp')
    if case == 'subject': claims['sub'] = 'not-a-user-id'
    key = 'wrong-signing-key-at-least-32-characters' if case == 'signature' else os.environ['JWT_SECRET_KEY']
    value = jwt.encode(claims, key, algorithm='HS256') if case != 'malformed' else 'not-a-jwt'
    headers = {} if case == 'absent' else {'Authorization': 'Bearer ' + value}
    for client, path in ((stack.account, '/users/me'), (stack.account, '/accounts/me'),
                         (stack.payment, '/api/v1/payments'), (stack.tuition, '/api/v1/tuition/SV2026001')):
        assert client.get(path, headers=headers).status_code == 401


def test_profile_balance_and_completed_history_are_scoped_to_the_logged_in_user(stack, credentials):
    payment = stack.create(); key = payment['payment_id']
    stack.verify(key)
    assert stack.process(key).json()['status'] == 'SUCCEEDED'
    # Client-supplied user/account IDs never choose the owner of /me or history.
    assert stack.account.get('/users/me?user_id=2', headers=stack.headers).json()['id'] == 1
    assert stack.account.get('/accounts/me?account_id=2', headers=stack.headers).json()['balance'] == '1000000.00'
    history = stack.payment.get('/api/v1/payments?payer_user_id=2', headers=stack.headers).json()
    assert len(history['items']) == 1 and history['items'][0]['status'] == 'SUCCEEDED'
    other = {'Authorization': 'Bearer ' + token(2)}
    assert stack.account.get('/users/me', headers=other).json()['id'] == 2
    assert stack.account.get('/accounts/me', headers=other).json()['balance'] == '10000000.00'
    assert stack.payment.get('/api/v1/payments', headers=other).json()['items'] == []
    assert stack.payment.get('/api/v1/payments/' + key, headers=other).status_code == 404
    assert stack.payment.get('/api/v1/payments?cursor=' + key, headers=other).status_code == 404
