import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from shared.database import sqlserver_url

database_url = os.getenv('ACCOUNT_DATABASE_URL') or sqlserver_url(os.getenv("DB_NAME", "account_db"))

if str(database_url).startswith('sqlite'):
    from sqlalchemy.pool import StaticPool
    engine = create_engine(database_url, connect_args={'check_same_thread': False}, poolclass=StaticPool)
else:
    engine = create_engine(database_url, pool_pre_ping=True)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass
