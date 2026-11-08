import os
import re
from itertools import count
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger
from sqlalchemy.ext.compiler import compiles

from services.account import database as account_db
from services.account.main import app as account_app
from services.account.models import Account, User
from services.payment import database as payment_db
from services.payment.clients import Services, UpstreamError, get_services
from services.payment.main import app as payment_app
from services.payment.mailer import MailError, get_mailer
from services.tuition import database as tuition_db
from services.tuition.main import app as tuition_app
from services.tuition.models import Student, TuitionInvoice


@compiles(BigInteger, 'sqlite')
def sqlite_bigint(element, compiler, **kw):
    return 'INTEGER'


def token(user_id=1):
    now = datetime.now(timezone.utc)
    return jwt.encode({'sub': str(user_id), 'iat': now, 'exp': now + timedelta(minutes=30),
        'iss': 'account-service', 'aud': 'ibanking'}, os.environ['JWT_SECRET_KEY'], algorithm='HS256')


class TestServices(Services):
    __test__ = False

    def __init__(self, account, tuition):
        self.clients = {'account': account, 'tuition': tuition}
        self.faults = {}

    def request(self, service, method, path, *, token=None, body=None):
        fault = self.faults.pop((service, path), None)
        if fault == 'before':
            raise UpstreamError(503, 'Simulated service outage')
        if fault == 'conflict':
            raise UpstreamError(409, 'Simulated terminal conflict')
        headers = {'Authorization': 'Bearer ' + token} if token else {'X-Internal-Key': os.environ['INTERNAL_API_KEY']}
        response = self.clients[service].request(method, path, headers=headers, json=body)
        if response.status_code >= 400:
            raise UpstreamError(response.status_code, str(response.json()['detail']))
        if fault == 'after':
            raise UpstreamError(503, 'Simulated lost response after commit')
        if fault == 'conflict_after':
            raise UpstreamError(409, 'Simulated ambiguous conflict after commit')
        return response.json()


class Stack:
    def __init__(self, account, tuition, payment):
        self.account, self.tuition, self.payment = account, tuition, payment
        self.services = TestServices(account, tuition)
        self.headers = {'Authorization': 'Bearer ' + token()}
        self.internal = {'X-Internal-Key': os.environ['INTERNAL_API_KEY']}
        self.mailer = TestMailer()

    def create(self, key=None):
        key = key or str(uuid4())
        body = {'mssv': 'SV2026001', 'selection_mode': 'ALL_UNPAID', 'terms_accepted': True}
        response = self.payment.post('/api/v1/payments', headers={**self.headers, 'Idempotency-Key': key}, json=body)
        assert response.status_code == 201, response.text
        return response.json()

    def verify(self, key):
        response = self.payment.post(f'/api/v1/payments/{key}/send-otp', headers=self.headers)
        assert response.status_code == 202, response.text
        code = re.search(r'Mã OTP của bạn:\s*(\d{6})', self.mailer.messages[-1]['body']).group(1)
        response = self.payment.post(f'/api/v1/payments/{key}/verify-otp', headers=self.headers,
            json={'challenge_id': response.json()['challenge_id'], 'otp': code})
        assert response.status_code == 200, response.text

    def process(self, key):
        return self.payment.post(f'/api/v1/payments/{key}/process', headers=self.headers)


class TestMailer:
    __test__ = False

    def __init__(self):
        self.messages = []
        self.fail = False

    def send(self, **message):
        if self.fail:
            raise MailError('SimulatedSMTPFailure')
        self.messages.append(message)


@pytest.fixture
def stack(monkeypatch):
    from services.payment import routes
    codes = count(123456)
    monkeypatch.setattr(routes, 'generate_otp', lambda: f'{next(codes):06d}')
    for database in (payment_db, tuition_db, account_db):
        database.Base.metadata.drop_all(database.engine)
        database.Base.metadata.create_all(database.engine)
    with account_db.SessionLocal.begin() as db:
        db.add_all([User(id=value, username=f'user{value}', password_hash='unused', full_name=f'User {value}',
            email=f'user{value}@example.test', email_verified_at=datetime.now(timezone.utc).replace(tzinfo=None), phone='0900000001', is_active=True) for value in (1, 2)])
        db.flush()
        db.add_all([Account(id=value, user_id=value, account_number=f'100000000{value}', balance=Decimal('10000000.00'), status='ACTIVE') for value in (1, 2)])
    with tuition_db.SessionLocal.begin() as db:
        db.add(Student(id=1, mssv='SV2026001', full_name='Sinh viên Demo'))
        db.flush()
        for index, amount in enumerate(('2000000.00', '3000000.00', '4000000.00'), start=1):
            db.add(TuitionInvoice(id=index, student_id=1, semester=f'HK{index}', amount_due=Decimal(amount)))
    with TestClient(account_app) as account, TestClient(tuition_app) as tuition, TestClient(payment_app) as payment:
        result = Stack(account, tuition, payment)
        payment_app.dependency_overrides[get_services] = lambda: result.services
        payment_app.dependency_overrides[get_mailer] = lambda: result.mailer
        account_app.dependency_overrides[get_mailer] = lambda: result.mailer
        try:
            yield result
        finally:
            payment_app.dependency_overrides.clear()
            account_app.dependency_overrides.clear()
    for database in (payment_db, tuition_db, account_db):
        database.Base.metadata.drop_all(database.engine)
