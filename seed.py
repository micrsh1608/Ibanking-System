from decimal import Decimal

from app.db.database import Base, SessionLocal, engine
from app.models import Student, Tuition


Base.metadata.create_all(bind=engine)

db = SessionLocal()

students = [
    {
        "mssv": "52200001",
        "full_name": "Nguyen Van An",
        "phone": "0900000001",
        "email": "an@gmail.com",
        "amount": Decimal("12500000"),
    },
    {
        "mssv": "52200002",
        "full_name": "Tran Thi Binh",
        "phone": "0900000002",
        "email": "binh@gmail.com",
        "amount": Decimal("9800000"),
    },
    {
        "mssv": "52200003",
        "full_name": "Le Van Cuong",
        "phone": "0900000003",
        "email": "cuong@gmail.com",
        "amount": Decimal("15000000"),
    },
]

for item in students:
    student = db.query(Student).filter(Student.mssv == item["mssv"]).first()

    if student is None:
        student = Student(
            mssv=item["mssv"],
            full_name=item["full_name"],
            phone=item["phone"],
            email=item["email"],
        )
        db.add(student)
        db.flush()

        db.add(
            Tuition(
                student_id=student.id,
                amount=item["amount"],
                status="UNPAID",
            )
        )

db.commit()
db.close()

print("Seed data inserted successfully.")
print("MSSV: 52200001 | email: an@gmail.com | 12,500,000")
print("MSSV: 52200002 | email: binh@gmail.com | 9,800,000")
print("MSSV: 52200003 | email: cuong@gmail.com | 15,000,000")
