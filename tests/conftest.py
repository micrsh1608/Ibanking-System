"""Isolate automated tests from private settings and the real SQL Server."""
import os

os.environ["DB_SERVER"] = "unit-tests.invalid"
os.environ["TUITION_DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["JWT_SECRET_KEY"] = "test-secret-only-for-isolated-unit-tests-32chars"
os.environ["INTERNAL_API_KEY"] = "test-internal-key-only-for-isolated-tests-32chars"
os.environ['PAYMENT_DATABASE_URL'] = 'sqlite+pysqlite:///:memory:'
os.environ['ACCOUNT_DATABASE_URL'] = 'sqlite+pysqlite:///:memory:'
os.environ['PAYMENT_RECOVERY_ENABLED'] = 'false'
os.environ['PAYMENT_MAIL_ENABLED'] = 'false'
