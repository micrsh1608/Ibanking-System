"""Add fresh unpaid demo tuition without resetting users, money or paid invoices."""
import argparse
from decimal import Decimal
import json

from sqlalchemy import select
from infra.docker.demo_admin import require_local_docker


def prepare(username='huy'):
    require_local_docker()
    from services.account.database import SessionLocal as AccountSession
    from services.account.models import Account, User
    from services.tuition.database import SessionLocal as TuitionSession
    from services.tuition.models import Student, TuitionInvoice
    total = Decimal('1000000.00')
    with AccountSession() as db:
        user = db.scalar(select(User).where(User.username == username))
        account = db.scalar(select(Account).where(Account.user_id == user.id)) if user else None
        if not user or not account or not user.is_active or account.status != 'ACTIVE':
            raise RuntimeError('Need an existing active payer/account; explicitly seed or provision the demo first.')
        if not user.email_verified:
            raise RuntimeError('Verify the payer email in Personal information before preparing the live demo.')
        if account.balance < total:
            raise RuntimeError('Payer needs at least 1,000,000 VND. Existing balances are never changed by this command.')
        balance = account.balance
    with TuitionSession.begin() as db:
        from services.tuition.seed import require_normalized_students
        require_normalized_students(db)
        for number in range(1014, 10000):
            mssv = f'SV2026{number}'
            student = db.scalar(select(Student).where(Student.mssv == mssv))
            if student is None:
                student = Student(mssv=mssv, full_name='Nguyễn Hoàng Phúc')
                db.add(student)
                db.flush()
                for semester, amount in [('2026-2027-HK1', '400000.00'), ('2026-2027-HK2', '600000.00')]:
                    db.add(TuitionInvoice(student_id=student.id, semester=semester,
                        amount_due=Decimal(amount), status='UNPAID', version=1))
                db.flush()
            rows = list(db.scalars(select(TuitionInvoice).where(TuitionInvoice.student_id == student.id).order_by(TuitionInvoice.id)))
            if len(rows) == 2 and all(row.status == 'UNPAID' for row in rows) and sum(row.amount_due for row in rows) == total:
                break
        else:
            raise RuntimeError('No unused student code remains in the 2026 sample dataset.')
        return {'ready': True, 'payer_username': username, 'payer_email_verified': True,
                'mssv': mssv, 'student_name': student.full_name,
                'invoices': [{'id': row.id, 'semester': row.semester, 'amount': format(row.amount_due, '.2f'), 'status': row.status} for row in rows],
                'total': format(total, '.2f'), 'balance_before': format(balance, '.2f'),
                'expected_balance_after': format(balance-total, '.2f'),
                'note': 'No payment or email was sent; existing balances, profiles, paid tuition and history were preserved.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--username', default='huy')
    print(json.dumps(prepare(parser.parse_args().username), ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
