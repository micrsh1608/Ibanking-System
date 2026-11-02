"""Small forward-only revision runner; revisions execute atomically per service DB."""
from sqlalchemy import Column, DateTime, MetaData, String, Table, select

from shared.locking import transaction_lock
from shared.time import utcnow

metadata = MetaData()
revisions = Table("schema_revisions", metadata,
    Column("revision", String(80), primary_key=True),
    Column("applied_at", DateTime, nullable=False))


def upgrade(engine, steps):
    from sqlalchemy.orm import Session
    with engine.begin() as connection:
        with Session(bind=connection) as db:
            transaction_lock(db, "schema-upgrade")
            metadata.create_all(connection)
            applied = set(connection.execute(select(revisions.c.revision)).scalars())
            for revision, migrate in steps:
                if revision not in applied:
                    migrate(connection)
                    connection.execute(revisions.insert().values(revision=revision, applied_at=utcnow()))
