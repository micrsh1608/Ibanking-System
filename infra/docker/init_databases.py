"""Prepare only the three databases belonging to the local Docker demo."""
import os
from sqlalchemy import create_engine

from shared.database import sqlserver_url


def prepare_schema():
    engine = create_engine(sqlserver_url("master"), isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            for name in ("account_db", "payment_db", "tuition_db"):
                connection.exec_driver_sql(
                    f"IF DB_ID(N'{name}') IS NULL CREATE DATABASE [{name}]"
                )
    finally:
        engine.dispose()

    # Import after databases exist. Every service owns its own metadata/engine.
    from services.account.migrate import migrate as account_migrate
    from services.payment.migrate import migrate as payment_migrate
    from services.tuition.migrate import migrate as tuition_migrate
    account_migrate()
    payment_migrate()
    tuition_migrate()


def seed_demo():
    from services.account.seed import init_db as seed_account
    from services.payment.init_db import init_db as init_payment
    from services.tuition.seed import seed as seed_tuition

    seed_account()
    init_payment()
    seed_tuition()


def main():
    prepare_schema()
    if os.getenv('IBANKING_SEED_DEMO', 'false').lower() == 'true':
        seed_demo()
    else:
        print('Schemas ready. Demo seeding is disabled; existing data is unchanged.')


if __name__ == "__main__":
    main()
