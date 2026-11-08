from sqlalchemy import create_engine, inspect, text


def test_account_email_migration_keeps_existing_profile_but_does_not_claim_ownership(monkeypatch):
    from services.account import migrate
    engine=create_engine('sqlite+pysqlite:///:memory:')
    with engine.begin() as connection:
        connection.exec_driver_sql('CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(255), full_name VARCHAR(100))')
        connection.exec_driver_sql("INSERT INTO users VALUES (1,'legacy@example.test','Existing User')")
    monkeypatch.setattr(migrate,'engine',engine)
    migrate.migrate();migrate.migrate()
    with engine.connect() as connection:
        assert connection.exec_driver_sql('SELECT email,full_name,email_verified_at,pending_email,email_code_attempts FROM users').one()==('legacy@example.test','Existing User',None,None,0)
        assert connection.exec_driver_sql('SELECT COUNT(*) FROM schema_revisions').scalar()==4


def test_tuition_upgrade_preserves_old_rows_and_is_repeatable(monkeypatch):
    from services.tuition import migrate
    engine = create_engine('sqlite+pysqlite:///:memory:')
    with engine.begin() as connection:
        connection.exec_driver_sql('CREATE TABLE tuition_invoices (id INTEGER PRIMARY KEY)')
        connection.exec_driver_sql('INSERT INTO tuition_invoices(id) VALUES (42)')
    monkeypatch.setattr(migrate, 'engine', engine)
    migrate.migrate()
    migrate.migrate()
    with engine.connect() as connection:
        assert connection.exec_driver_sql('SELECT id, version FROM tuition_invoices').all() == [(42, 1)]
        assert connection.exec_driver_sql('SELECT COUNT(*) FROM schema_revisions').scalar() == 2


def test_payment_upgrade_preserves_legacy_tables(monkeypatch):
    from services.payment import migrate
    engine = create_engine('sqlite+pysqlite:///:memory:')
    with engine.begin() as connection:
        connection.exec_driver_sql('CREATE TABLE payment_transactions (id INTEGER PRIMARY KEY)')
        connection.exec_driver_sql('INSERT INTO payment_transactions(id) VALUES (7)')
    monkeypatch.setattr(migrate, 'engine', engine)
    migrate.migrate()
    migrate.migrate()
    with engine.connect() as connection:
        assert connection.exec_driver_sql('SELECT id FROM payment_transactions').scalar() == 7
        assert connection.exec_driver_sql('SELECT COUNT(*) FROM schema_revisions').scalar() == 5
    assert {'payments', 'payment_items', 'email_outbox'} <= set(inspect(engine).get_table_names())


def test_consent_migration_keeps_existing_payment_and_unknown_acceptance(monkeypatch):
    from services.payment import migrate
    engine=create_engine('sqlite+pysqlite:///:memory:')
    with engine.begin() as connection:
        connection.exec_driver_sql('CREATE TABLE payments (payment_id VARCHAR(36) PRIMARY KEY, status VARCHAR(32), updated_at DATETIME, completed_at DATETIME, otp_hash VARCHAR(64), challenge_id VARCHAR(36), otp_expires_at DATETIME, otp_last_sent_at DATETIME, otp_attempts INTEGER)')
        connection.exec_driver_sql("INSERT INTO payments(payment_id,status,updated_at) VALUES('legacy','SUCCEEDED','2026-11-02')")
    monkeypatch.setattr(migrate,'engine',engine)
    migrate.migrate(); migrate.migrate()
    with engine.connect() as connection:
        assert connection.exec_driver_sql('SELECT payment_id,status,terms_version,terms_accepted_at FROM payments').one()==('legacy','SUCCEEDED',None,None)


def test_otp_registry_migration_invalidates_only_old_pending_codes_and_is_repeatable():
    from services.payment.migrate import unique_otp_codes
    engine=create_engine('sqlite+pysqlite:///:memory:')
    with engine.begin() as connection:
        connection.exec_driver_sql('CREATE TABLE payments (payment_id VARCHAR(36) PRIMARY KEY, status VARCHAR(32), otp_hash VARCHAR(64), challenge_id VARCHAR(36), otp_expires_at DATETIME, otp_last_sent_at DATETIME, otp_attempts INTEGER)')
        connection.exec_driver_sql("INSERT INTO payments VALUES('pending','PENDING_OTP','old-hash','old-challenge','2030-01-01','2026-11-04',2)")
        connection.exec_driver_sql("INSERT INTO payments VALUES('done','SUCCEEDED',NULL,NULL,NULL,NULL,0)")
        unique_otp_codes(connection)
        assert connection.exec_driver_sql("SELECT status,otp_hash,challenge_id,otp_expires_at,otp_attempts FROM payments WHERE payment_id='pending'").one()==('PENDING_OTP',None,None,None,0)
        connection.exec_driver_sql("UPDATE payments SET otp_hash='new-hash',challenge_id='new-challenge',otp_fingerprint='new-fingerprint',otp_expires_at='2030-01-01' WHERE payment_id='pending'")
        unique_otp_codes(connection)
        assert connection.exec_driver_sql("SELECT otp_hash,challenge_id,otp_fingerprint FROM payments WHERE payment_id='pending'").one()==('new-hash','new-challenge','new-fingerprint')
        assert connection.exec_driver_sql("SELECT status FROM payments WHERE payment_id='done'").scalar()=='SUCCEEDED'
