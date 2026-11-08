"""Local Docker demo data operations. Never an HTTP account-registration API."""
import argparse
import json
import os
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import create_engine, select

from shared.database import sqlserver_url

DATABASES = ('account_db', 'payment_db', 'tuition_db')


def require_local_docker():
    expected = {'DB_SERVER': 'sqlserver,1433', 'DB_NAME': 'account_db',
        'PAYMENT_DB_NAME': 'payment_db', 'TUITION_DB_NAME': 'tuition_db'}
    if any(os.getenv(key) != value for key, value in expected.items()):
        raise RuntimeError('Refusing operation outside the fixed local Docker database configuration')
    if any(os.getenv(key) for key in ('ACCOUNT_DATABASE_URL', 'PAYMENT_DATABASE_URL', 'TUITION_DATABASE_URL')):
        raise RuntimeError('Refusing custom database URL overrides')


def inventory():
    result = {}
    for name in DATABASES:
        engine = create_engine(sqlserver_url(name))
        try:
            with engine.connect() as connection:
                tables = connection.exec_driver_sql('SELECT SCHEMA_NAME(schema_id), name FROM sys.tables ORDER BY name').all()
                result[name] = {}
                for schema, table in tables:
                    quoted = '[' + schema.replace(']', ']]') + '].[' + table.replace(']', ']]') + ']'
                    result[name][table] = connection.exec_driver_sql('SELECT COUNT_BIG(*) FROM ' + quoted).scalar_one()
        finally:
            engine.dispose()
    return result


def reset_databases(confirmation):
    require_local_docker()
    if confirmation != 'ibanking-demo':
        raise ValueError('Reset requires the exact confirmation token ibanking-demo')
    engine = create_engine(sqlserver_url('master'), isolation_level='AUTOCOMMIT')
    try:
        with engine.connect() as connection:
            # Names are a fixed allowlist; never substitute a client database name.
            for name in DATABASES:
                connection.exec_driver_sql(f"IF DB_ID(N'{name}') IS NOT NULL BEGIN ALTER DATABASE [{name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [{name}]; END")
                connection.exec_driver_sql(f'CREATE DATABASE [{name}]')
    finally:
        engine.dispose()
    from infra.docker.init_databases import prepare_schema
    prepare_schema()
    result = inventory()
    if any(count for tables in result.values() for table, count in tables.items() if table != 'schema_revisions'):
        raise RuntimeError('The reset did not leave all business tables empty')
    return result


class NewTuition(BaseModel):
    mssv: str = Field(min_length=1, max_length=24, pattern=r'^[A-Za-z0-9_-]+$')
    student_name: str = Field(min_length=2, max_length=150, pattern=r'^[^\x00-\x1f\x7f]+$')
    semester: str = Field(min_length=1, max_length=32, pattern=r'^[^\x00-\x1f\x7f]+$')
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)

    @field_validator('mssv', 'student_name', 'semester', mode='before')
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value


def add_tuition(data):
    require_local_docker()
    from services.tuition.database import SessionLocal
    from services.tuition.models import Student, TuitionInvoice
    with SessionLocal.begin() as db:
        student = db.scalar(select(Student).where(Student.mssv == data.mssv))
        if student is None:
            student = Student(mssv=data.mssv, full_name=data.student_name)
            db.add(student)
            db.flush()
        if db.scalar(select(TuitionInvoice.id).where(TuitionInvoice.student_id == student.id,
                TuitionInvoice.semester == data.semester)) is not None:
            raise ValueError('MSSV and semester already exist; use a new semester instead of editing a paid invoice')
        invoice = TuitionInvoice(student_id=student.id, semester=data.semester, amount_due=data.amount, status='UNPAID', version=1)
        db.add(invoice)
        db.flush()
        return {'mssv': student.mssv, 'student_name': student.full_name, 'invoice_id': invoice.id,
            'semester': invoice.semester, 'amount': format(invoice.amount_due, '.2f'), 'status': 'UNPAID'}


def create_test_account(username, email):
    require_local_docker()
    from services.account.seed import create_test_account as create
    return create(username=username, email=email)


def main():
    parser = argparse.ArgumentParser()
    actions = parser.add_subparsers(dest='action', required=True)
    reset = actions.add_parser('reset')
    reset.add_argument('--confirm-local-reset', required=True)
    actions.add_parser('status')
    actions.add_parser('seed')
    test_account = actions.add_parser('create-test-account')
    test_account.add_argument('--username', default='huy2')
    test_account.add_argument('--email', default='')
    normalize = actions.add_parser('normalize-tuition')
    normalize.add_argument('--confirm-local-rewrite', required=True)
    normalize_accounts = actions.add_parser('normalize-accounts')
    normalize_accounts.add_argument('--confirm-local-rewrite', required=True)
    tuition = actions.add_parser('add-tuition')
    for argument in ('mssv', 'student-name', 'semester', 'amount'):
        tuition.add_argument('--' + argument, required=True)
    args = parser.parse_args()
    require_local_docker()
    if args.action == 'reset':
        result = reset_databases(args.confirm_local_reset)
    elif args.action == 'seed':
        from infra.docker.init_databases import prepare_schema, seed_demo
        prepare_schema()
        seed_demo()
        result = inventory()
    elif args.action == 'create-test-account':
        result = create_test_account(args.username, args.email)
    elif args.action == 'normalize-tuition':
        from infra.docker.normalize_tuition import normalize
        result = normalize(args.confirm_local_rewrite)
    elif args.action == 'normalize-accounts':
        from infra.docker.normalize_accounts import normalize
        result = normalize(args.confirm_local_rewrite)
    elif args.action == 'add-tuition':
        result = add_tuition(NewTuition(mssv=args.mssv, student_name=args.student_name, semester=args.semester, amount=args.amount))
    else:
        result = inventory()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
