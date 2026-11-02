from decimal import Decimal

from sqlalchemy import select
from services.tuition.database import Base, SessionLocal, engine
from services.tuition.models import Student, TuitionInvoice


def seed():
    from services.tuition.migrate import migrate
    migrate()
    with SessionLocal.begin() as db:
        student = db.scalar(select(Student).where(Student.mssv == 'SV2026001'))
        if student is None:
            student = Student(mssv='SV2026001', full_name='Sinh viên Demo')
            db.add(student)
            db.flush()
        for semester, amount in [('2026-2027-HK1', '2000000.00'), ('2026-2027-HK2', '3000000.00')]:
            existing = db.scalar(select(TuitionInvoice).where(
                TuitionInvoice.student_id == student.id, TuitionInvoice.semester == semester))
            if existing is None:
                db.add(TuitionInvoice(student_id=student.id, semester=semester, amount_due=Decimal(amount), status='UNPAID'))
    print('Tuition Service: đã tạo bảng và dữ liệu mẫu (SV2026001).')


if __name__ == '__main__':
    seed()
