from decimal import Decimal

from app.db.database import SessionLocal
from app.models import Student, Tuition


def insert_student():
    db = SessionLocal()

    student = Student(
        mssv="TEST001",
        full_name="Test Student",
        phone="0900000000",
        email="test@gmail.com",
    )
    db.add(student)
    db.flush()

    db.add(
        Tuition(
            student_id=student.id,
            amount=Decimal("5000000"),
            status="UNPAID",
        )
    )

    db.commit()
    db.close()


def test_lookup_tuition(client):
    insert_student()

    response = client.get("/api/v1/tuition/TEST001")

    assert response.status_code == 200
    data = response.json()
    assert data["mssv"] == "TEST001"
    assert data["status"] == "UNPAID"
    assert data["amount"] == "5000000.00"


def test_lookup_unknown_student(client):
    response = client.get("/api/v1/tuition/UNKNOWN")
    assert response.status_code == 404
