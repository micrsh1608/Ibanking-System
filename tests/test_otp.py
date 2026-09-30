from app.db.database import SessionLocal
from app.models import OTP
from datetime import datetime, timedelta


def test_otp_wrong_code(client, monkeypatch):
    # OTP endpoint needs a student; use seed-like record.
    from app.models import Student, Tuition
    from decimal import Decimal

    db = SessionLocal()
    student = Student(
        mssv="OTP001",
        full_name="OTP Student",
        email="otp@gmail.com",
    )
    db.add(student)
    db.flush()
    db.add(Tuition(student_id=student.id, amount=Decimal("1000000"), status="UNPAID"))
    db.commit()
    db.close()

    response = client.post(
        "/api/v1/otp/send",
        json={
            "transaction_id": "TX-OTP-001",
            "mssv": "OTP001",
            "email": "otp@gmail.com",
        },
    )

    assert response.status_code == 200

    response = client.post(
        "/api/v1/otp/verify",
        json={
            "transaction_id": "TX-OTP-001",
            "otp": "000000",
        },
    )

    assert response.status_code == 400


def test_otp_expired(client):
    db = SessionLocal()
    db.add(
        OTP(
            transaction_id="TX-EXPIRED",
            mssv="OTP001",
            email="otp@gmail.com",
            otp_code="123456",
            expires_at=datetime.utcnow() - timedelta(minutes=1),
            used=False,
        )
    )
    db.commit()
    db.close()

    response = client.post(
        "/api/v1/otp/verify",
        json={
            "transaction_id": "TX-EXPIRED",
            "otp": "123456",
        },
    )

    assert response.status_code == 400
