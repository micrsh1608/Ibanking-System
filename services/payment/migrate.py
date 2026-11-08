from services.payment.database import Base, engine
from services.payment.models import payment
from shared.migrations import upgrade
from sqlalchemy import inspect


def email_outbox(connection):
    payment.EmailOutbox.__table__.create(connection, checkfirst=True)
    if 'completed_at' not in {column['name'] for column in inspect(connection).get_columns('payments')}:
        connection.exec_driver_sql('ALTER TABLE payments ADD completed_at DATETIME NULL')
    connection.exec_driver_sql("UPDATE payments SET completed_at=updated_at WHERE status='SUCCEEDED' AND completed_at IS NULL")


def payment_terms(connection):
    columns = {column['name'] for column in inspect(connection).get_columns('payments')}
    if 'terms_version' not in columns:
        connection.exec_driver_sql('ALTER TABLE payments ADD terms_version VARCHAR(32) NULL')
    if 'terms_accepted_at' not in columns:
        connection.exec_driver_sql('ALTER TABLE payments ADD terms_accepted_at DATETIME NULL')
    # Keep legacy consent unknown; never invent acceptance for old transactions.


def unique_otp_codes(connection):
    if 'otp_fingerprint' not in {column['name'] for column in inspect(connection).get_columns('payments')}:
        connection.exec_driver_sql('ALTER TABLE payments ADD otp_fingerprint VARCHAR(64) NULL')
        # Previous challenges have only a transaction-bound hash, so their code
        # cannot join the equality registry. Require a fresh code, preserving
        # payment intents and every existing monetary/tuition outcome.
    connection.exec_driver_sql("UPDATE payments SET otp_hash=NULL, challenge_id=NULL, otp_expires_at=NULL, otp_last_sent_at=NULL, otp_attempts=0 WHERE status='PENDING_OTP' AND otp_fingerprint IS NULL AND otp_hash IS NOT NULL")
    for index in payment.PaymentTransaction.__table__.indexes:
        if index.name == 'uq_payments_otp_fingerprint':
            index.create(connection, checkfirst=True)


def email_channels(connection):
    # Preserve recipients, challenge deadlines and every financial outcome.
    # Legacy events retain the configured transport until a new snapshot is made.
    for table in ('payments', 'email_outbox'):
        columns = {column['name'] for column in inspect(connection).get_columns(table)}
        if 'email_channel' not in columns:
            connection.exec_driver_sql(
                f"ALTER TABLE {table} ADD email_channel VARCHAR(12) NOT NULL DEFAULT 'configured'")


def migrate():
    # Legacy prototype tables remain intact; live code uses only payments/payment_items.
    upgrade(engine, [
        ('20261102_payment_snapshots', lambda connection: Base.metadata.create_all(connection)),
        ('20261105_email_outbox', email_outbox),
        ('20261103_full_tuition_terms_v1', payment_terms),
        ('20261104_unique_active_otp', unique_otp_codes),
        ('20261106_payment_email_channels', email_channels),
    ])


if __name__ == '__main__':
    migrate()
