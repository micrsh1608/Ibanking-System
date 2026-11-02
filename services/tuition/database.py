"""Tuition's own SQL Server connection. Uses SQLite only if explicitly configured for tests."""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from shared.database import sqlserver_url


def database_url():
    test_url = os.getenv('TUITION_DATABASE_URL')
    if test_url:
        return test_url

    return sqlserver_url(os.getenv('TUITION_DB_NAME', 'tuition_db'), credential_prefix='TUITION_DB')


url = database_url()
if str(url).startswith('sqlite'):
    from sqlalchemy.pool import StaticPool
    engine = create_engine(url, connect_args={'check_same_thread': False}, poolclass=StaticPool)
else:
    engine = create_engine(url, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    with SessionLocal() as db:
        yield db
