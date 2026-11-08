from sqlalchemy import inspect

from services.tuition.database import Base, engine
from services.tuition import models
from shared.migrations import upgrade


def add_invoice_version(connection):
    if 'version' not in {column['name'] for column in inspect(connection).get_columns('tuition_invoices')}:
        connection.exec_driver_sql('ALTER TABLE tuition_invoices ADD version INTEGER NOT NULL DEFAULT 1')


def disable_identity_cache(connection):
    if connection.dialect.name == 'mssql':
        # Avoid jumps of 1,000 in the local teaching dataset after a restart.
        # SQL Server requires this setting outside any user transaction.
        connection.exec_driver_sql("IF EXISTS (SELECT 1 FROM sys.database_scoped_configurations "
            "WHERE name = 'IDENTITY_CACHE' AND value = 1) "
            'ALTER DATABASE SCOPED CONFIGURATION SET IDENTITY_CACHE = OFF')


def migrate():
    if engine.dialect.name == 'mssql':
        with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
            disable_identity_cache(connection)
    upgrade(engine, [
        ('20261102_tuition_reservations', lambda connection: Base.metadata.create_all(connection)),
        ('20261103_invoice_version', add_invoice_version),
    ])


if __name__ == '__main__':
    migrate()
