from sqlalchemy import inspect

from services.tuition.database import Base, engine
from services.tuition import models
from shared.migrations import upgrade


def add_invoice_version(connection):
    if 'version' not in {column['name'] for column in inspect(connection).get_columns('tuition_invoices')}:
        connection.exec_driver_sql('ALTER TABLE tuition_invoices ADD version INTEGER NOT NULL DEFAULT 1')


def migrate():
    upgrade(engine, [
        ('20261102_tuition_reservations', lambda connection: Base.metadata.create_all(connection)),
        ('20261103_invoice_version', add_invoice_version),
    ])


if __name__ == '__main__':
    migrate()
