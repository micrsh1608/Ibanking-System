from sqlalchemy import create_engine, inspect, text


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
        assert connection.exec_driver_sql('SELECT COUNT(*) FROM schema_revisions').scalar() == 2
    assert {'payments', 'payment_items', 'email_outbox'} <= set(inspect(engine).get_table_names())
