"""Tuition seed data, including the main application's demo catalog."""
from decimal import Decimal

from sqlalchemy import select
from services.tuition.database import SessionLocal
from services.tuition.models import Student, TuitionInvoice


class DemoTuitionSeedError(ValueError):
    pass


STUDENT_CATALOG = (
    ('SV20261001', 'Nguyễn Minh An', ('2500000.00',)),
    ('SV20261002', 'Trần Ngọc Linh', ('3500000.00',)),
    ('SV20261003', 'Lê Hoàng Nam', ('7000000.00',)),
    ('SV20261004', 'Phạm Thu Hà', ('7000000.00',)),
    ('SV20261005', 'Hoàng Gia Bảo', ('2000000.00', '3000000.00')),
    ('SV20261006', 'Võ Khánh Vy', ('1000000.00',)),
    ('SV20261007', 'Đặng Minh Quân', ('1000000.00',)),
    ('SV20261008', 'Bùi Ngọc Anh', ('2000000.00',)),
    ('SV20261009', 'Đỗ Đức Huy', ('1000000.00',)),
    ('SV20261010', 'Hồ Thảo Nhi', ('2000000.00',)),
    ('SV20261011', 'Dương Tuấn Kiệt', ('1000000.00',)),
    ('SV20261012', 'Ngô Phương Thảo', ('2000000.00',)),
)
BASE_STUDENT = ('SV20261013', 'Lê Minh Khang')
LEGACY_STUDENT_CODES = {
    'DEMO-BAL-A': 'SV20261003', 'DEMO-BAL-B': 'SV20261004',
    'DEMO-SAME': 'SV20261005', 'DEMO-SMTP': 'SV20261006',
    **{f'DEMO{index:02d}': f'SV2026{index + 1002}' for index in range(5, 11)},
    'SV2026001': BASE_STUDENT[0],
}


def student_plan():
    return [(mssv, list(amounts)) for mssv, _name, amounts in STUDENT_CATALOG]


def require_normalized_students(db):
    if db.scalar(select(Student.id).where(Student.mssv.in_(LEGACY_STUDENT_CODES)).limit(1)) is not None:
        raise DemoTuitionSeedError('Legacy student data found. Run demo-data.ps1 -NormalizeTuition before seeding.')


def seed_demo_students(session_factory=None):
    """Add missing students/invoices; never reopen a paid or reserved invoice."""
    factory = session_factory or SessionLocal
    students = []
    names = {mssv: name for mssv, name, _amounts in STUDENT_CATALOG}
    with factory.begin() as db:
        require_normalized_students(db)
        for mssv, amounts in student_plan():
            name = names[mssv]
            student = db.scalar(select(Student).where(Student.mssv == mssv))
            if student is None:
                student = Student(mssv=mssv, full_name=name)
                db.add(student)
                db.flush()
            elif student.full_name != name:
                raise DemoTuitionSeedError('An existing demo MSSV is not owned by this catalog; its invoices were preserved.')
            for index, amount in enumerate(amounts, 1):
                semester = f'2026-2027-HK{index}'
                invoice = db.scalar(select(TuitionInvoice).where(TuitionInvoice.student_id == student.id,
                                                                TuitionInvoice.semester == semester))
                if invoice is None:
                    db.add(TuitionInvoice(student_id=student.id, semester=semester,
                                          amount_due=Decimal(amount), status='UNPAID', version=1))
                elif invoice.amount_due != Decimal(amount):
                    raise DemoTuitionSeedError('A catalog invoice amount was changed; it will not be overwritten.')
            db.flush()
            rows = list(db.scalars(select(TuitionInvoice).where(TuitionInvoice.student_id == student.id).order_by(TuitionInvoice.id)))
            students.append({'id': student.id, 'mssv': mssv, 'student_name': student.full_name,
                             'unpaid_total': format(sum((row.amount_due for row in rows if row.status == 'UNPAID'), Decimal('0')), '.2f'),
                             'invoices': [{'id': row.id, 'semester': row.semester, 'amount': format(row.amount_due, '.2f'),
                                           'status': row.status, 'paid_payment_id': row.paid_payment_id} for row in rows]})
    return students


def seed():
    from services.tuition.migrate import migrate
    migrate()
    with SessionLocal.begin() as db:
        require_normalized_students(db)
        student = db.scalar(select(Student).where(Student.mssv == BASE_STUDENT[0]))
        if student is None:
            student = Student(mssv=BASE_STUDENT[0], full_name=BASE_STUDENT[1])
            db.add(student)
            db.flush()
        for semester, amount in [('2026-2027-HK1', '2000000.00'), ('2026-2027-HK2', '3000000.00')]:
            existing = db.scalar(select(TuitionInvoice).where(
                TuitionInvoice.student_id == student.id, TuitionInvoice.semester == semester))
            if existing is None:
                db.add(TuitionInvoice(student_id=student.id, semester=semester, amount_due=Decimal(amount), status='UNPAID'))
    print(f'Tuition Service: đã tạo bảng và dữ liệu mẫu ({BASE_STUDENT[0]}).')


if __name__ == '__main__':
    seed()
