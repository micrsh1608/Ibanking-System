import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

connection_string = (
    f"DRIVER={{{os.environ['DB_DRIVER']}}};"
    f"SERVER={os.environ['DB_SERVER']};"
    f"DATABASE={os.getenv('PAYMENT_DB_NAME', 'payment_db')};"
    "Trusted_Connection=yes;"
    "Encrypt=yes;"
    "TrustServerCertificate=yes;"
)

DATABASE_URL = URL.create(
    "mssql+pyodbc",
    query={"odbc_connect": connection_string},
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()