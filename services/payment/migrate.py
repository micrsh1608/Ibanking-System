from services.payment.database import Base, engine
from services.payment.models import payment
from shared.migrations import upgrade
from sqlalchemy import inspect


def email_outbox(connection):
    payment.EmailOutbox.__table__.create(connection, checkfirst=True)
    if 'completed_at' not in {column['name'] for column in inspect(connection).get_columns('payments')}:
        connection.exec_driver_sql('ALTER TABLE payments ADD completed_at DATETIME NULL')
    connection.exec_driver_sql("UPDATE payments SET completed_at=updated_at WHERE status='SUCCEEDED' AND completed_at IS NULL")


def migrate():
    # Legacy prototype tables remain intact; live code uses only payments/payment_items.
    upgrade(engine, [
        ('20261102_payment_snapshots', lambda connection: Base.metadata.create_all(connection)),
        ('20261105_email_outbox', email_outbox),
    ])


if __name__ == '__main__':
    migrate()
