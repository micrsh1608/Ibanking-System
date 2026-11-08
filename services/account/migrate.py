from services.account.database import Base, engine
from services.account import models
from shared.migrations import upgrade
from sqlalchemy import inspect


def verified_email(connection):
    columns = {column['name'] for column in inspect(connection).get_columns('users')}
    additions = {'email_verified_at':'DATETIME NULL','pending_email':'VARCHAR(255) NULL',
        'email_challenge_id':'VARCHAR(36) NULL','email_code_hash':'VARCHAR(64) NULL',
        'email_code_expires_at':'DATETIME NULL','email_code_sent_at':'DATETIME NULL',
        'email_code_attempts':'INTEGER NOT NULL DEFAULT 0','email_pending_profile':'NVARCHAR(2000) NULL'}
    for name, definition in additions.items():
        if name not in columns:
            connection.exec_driver_sql(f'ALTER TABLE users ADD {name} {definition}')
    # Do not infer ownership of any existing email address.


def account_email_routes(connection):
    columns = {column['name'] for column in inspect(connection).get_columns('users')}
    if 'email_channel' not in columns:
        connection.exec_driver_sql("ALTER TABLE users ADD email_channel VARCHAR(12) NOT NULL DEFAULT 'configured'")
    if 'email_pending_channel' not in columns:
        connection.exec_driver_sql('ALTER TABLE users ADD email_pending_channel VARCHAR(12) NULL')
    # Existing rows and in-flight legacy proofs retain the configured route.
    if connection.dialect.name == 'mssql':
        connection.exec_driver_sql("""IF NOT EXISTS (
            SELECT 1 FROM sys.check_constraints WHERE name='ck_user_email_channel'
              AND parent_object_id=OBJECT_ID('users'))
            ALTER TABLE users ADD CONSTRAINT ck_user_email_channel
            CHECK (email_channel IN ('configured','smtp','mailpit'))""")


def smtp_only_accounts(connection):
    # A captured message never proved ownership of a real inbox. Preserve the
    # profile and money, but require a new proof after changing delivery routes.
    connection.exec_driver_sql("""UPDATE users SET email_channel='smtp',
        email_verified_at=NULL, pending_email=NULL, email_challenge_id=NULL,
        email_code_hash=NULL, email_code_expires_at=NULL, email_code_sent_at=NULL,
        email_code_attempts=0, email_pending_profile=NULL, email_pending_channel=NULL
        WHERE email_channel='mailpit' OR email_pending_channel='mailpit'""")
    connection.exec_driver_sql("UPDATE users SET email_channel='smtp' WHERE email_channel='configured'")


def disable_identity_cache(connection):
    if connection.dialect.name == 'mssql':
        # SQL Server requires this setting outside a user transaction.
        connection.exec_driver_sql("IF EXISTS (SELECT 1 FROM sys.database_scoped_configurations "
            "WHERE name = 'IDENTITY_CACHE' AND value = 1) "
            'ALTER DATABASE SCOPED CONFIGURATION SET IDENTITY_CACHE = OFF')


def migrate():
    if engine.dialect.name == 'mssql':
        with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
            disable_identity_cache(connection)
    upgrade(engine, [('20261104_account_cancellation', lambda connection: Base.metadata.create_all(connection)),
        ('20261105_verified_email', verified_email),
        ('20261106_account_email_routes', account_email_routes),
        ('20261107_smtp_only_accounts', smtp_only_accounts)])


if __name__ == '__main__':
    migrate()
