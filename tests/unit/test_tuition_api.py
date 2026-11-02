"""Independent smoke tests with an in-memory SQLite database. No SQL Server changes."""
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import jwt
from fastapi.testclient import TestClient
from services.tuition.database import Base, SessionLocal, engine
from services.tuition.main import app
from services.tuition.models import Student, TuitionInvoice


def _headers():
    now = datetime.now(timezone.utc)
    token = jwt.encode({
        'sub': '1', 'iat': now, 'exp': now + timedelta(minutes=5),
        'iss': 'account-service', 'aud': 'ibanking',
    }, os.environ['JWT_SECRET_KEY'], algorithm='HS256')
    return {'Authorization': f'Bearer {token}'}


def test_tuition_lookup_and_auth():
    Base.metadata.create_all(bind=engine)
    with SessionLocal.begin() as db:
        student = Student(mssv='SV2026001', full_name='Sinh viên Demo')
        db.add(student)
        db.flush()
        db.add(TuitionInvoice(student_id=student.id, semester='2026-2027-HK1', amount_due=Decimal('2000000.00'), status='UNPAID'))
    client = TestClient(app)
    assert client.get('/health').status_code == 200
    assert client.get('/api/v1/tuition/SV2026001').status_code == 401
    response = client.get('/api/v1/tuition/SV2026001', headers=_headers())
    assert response.status_code == 200, response.text
    assert Decimal(response.json()['total_unpaid']) == Decimal('2000000.00')
    assert client.get('/api/v1/tuition/NOTFOUND', headers=_headers()).status_code == 404
