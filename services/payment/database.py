import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from shared.database import sqlserver_url

DATABASE_URL = os.getenv('PAYMENT_DATABASE_URL') or sqlserver_url(os.getenv("PAYMENT_DB_NAME", "payment_db"))

if str(DATABASE_URL).startswith('sqlite'):
    from sqlalchemy.pool import StaticPool
    engine = create_engine(DATABASE_URL, connect_args={'check_same_thread': False}, poolclass=StaticPool)
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
