"""Explicit, offline rewrite of the local sample dataset, with SQL backups.

Student/invoice identities are reassigned together with every persisted reference
in Tuition and Payment. Account balances and ledger entries are never written.
This is an administration command, never a startup migration or an HTTP API.
"""
import hashlib
import json
import re
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import create_engine, text

from infra.docker.demo_admin import require_local_docker
from services.tuition.seed import BASE_STUDENT, LEGACY_STUDENT_CODES, STUDENT_CATALOG
from shared.database import sqlserver_url


TABLES = {
    'students': 'dbo.students',
    'invoices': 'dbo.tuition_invoices',
    'reservations': 'dbo.tuition_reservations',
    'reservation_items': 'dbo.tuition_reservation_items',
    'payments': 'payment_db.dbo.payments',
    'payment_items': 'payment_db.dbo.payment_items',
}


def fingerprint(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def build_plan(snapshot):
    """Validate ownership/references before producing any database writes."""
    rows = {key: [dict(row) for row in value] for key, value in snapshot.items()}
    if (any(row['status'] not in {'SUCCEEDED', 'FAILED', 'REFUNDED'} for row in rows['payments'])
            or any(row['status'] == 'RESERVED' for row in rows['invoices'] + rows['reservations'])):
        raise ValueError('Finish or cancel pending payments before normalizing tuition data.')

    names = {code: name for code, name, _amounts in STUDENT_CATALOG} | {BASE_STUDENT[0]: BASE_STUDENT[1]}
    used_codes = {row['mssv'] for row in rows['students'] if re.fullmatch(r'SV\d{8}', row['mssv'])}
    code_map, student_map, original_codes = {}, {}, {}
    next_number = 1014
    for row in sorted(rows['students'], key=lambda row: row['id']):
        old_code = row['mssv']
        original_codes[row['id']] = old_code
        if old_code in LEGACY_STUDENT_CODES:
            expected_name = 'Sinh viên Demo' if old_code == 'SV2026001' else 'iBanking demo catalog: ' + old_code
            if row['full_name'] != expected_name:
                raise ValueError('A legacy student is not owned by the sample dataset; no data was rewritten.')
            code = LEGACY_STUDENT_CODES[old_code]
            row['full_name'] = names[code]
        elif re.fullmatch(r'DEMO\d{8}(?:-\d+)?', old_code) and row['full_name'] == 'Sinh viên trình diễn':
            while f'SV2026{next_number}' in used_codes:
                next_number += 1
            if next_number > 9999:
                raise ValueError('No sample student code is available.')
            code = f'SV2026{next_number}'
            row['full_name'] = 'Nguyễn Hoàng Phúc'
        elif re.fullmatch(r'SV\d{8}', old_code):
            code = old_code
        else:
            raise ValueError('Unknown student code found; review it before rewriting the sample dataset.')
        if code != old_code and code in used_codes:
            raise ValueError('Both a legacy and a replacement MSSV exist; no students were merged.')
        used_codes.add(code)
        code_map[old_code] = code
        row['mssv'] = code

    rows['students'].sort(key=lambda row: row['mssv'])
    for new_id, row in enumerate(rows['students'], 1):
        student_map[row['id']] = new_id
        row['id'] = new_id
    students_by_code = {row['mssv']: row for row in rows['students']}

    original_invoices = {row['id']: dict(row) for row in rows['invoices']}
    invoice_map, semesters = {}, set()
    for row in rows['invoices']:
        if row['student_id'] not in student_map:
            raise ValueError('An invoice has no student; no data was rewritten.')
        row['student_id'] = student_map[row['student_id']]
        if re.fullmatch(r'(CATALOG|DEMO)-HK\d+', row['semester']):
            row['semester'] = '2026-2027-' + row['semester'].split('-', 1)[1]
        key = (row['student_id'], row['semester'])
        if key in semesters:
            raise ValueError('Semester normalization would create duplicate invoices.')
        semesters.add(key)
    rows['invoices'].sort(key=lambda row: (row['student_id'], row['id']))
    for new_id, row in enumerate(rows['invoices'], 1):
        invoice_map[row['id']] = new_id
        row['id'] = new_id
    invoices = {row['id']: row for row in rows['invoices']}

    original_payments = {row['payment_id']: dict(row) for row in rows['payments']}
    for row in rows['payments']:
        if row['mssv'] not in code_map:
            raise ValueError('A payment has no matching student; no data was rewritten.')
        row['mssv'] = code_map[row['mssv']]
        row['student_name'] = students_by_code[row['mssv']]['full_name']
        row['request_hash'] = fingerprint({'user_id': row['payer_user_id'], 'mssv': row['mssv'],
            'selection_mode': row['selection_mode'], 'invoice_ids': []})
    payment_items = {}
    for row in rows['payment_items']:
        invoice = original_invoices.get(row['invoice_id'])
        payment = original_payments.get(row['payment_id'])
        if (not invoice or not payment or payment['mssv'] != original_codes[invoice['student_id']]
                or row['amount'] != invoice['amount_due']):
            raise ValueError('A payment item does not match its student/invoice; no data was rewritten.')
        row['invoice_id'] = invoice_map[row['invoice_id']]
        row['semester'] = invoices[row['invoice_id']]['semester']
        payment_items[(row['payment_id'], row['invoice_id'])] = row
    groups = {}
    for row in rows['reservation_items']:
        if row['invoice_id'] not in invoice_map:
            raise ValueError('A reservation refers to an unknown invoice.')
        row['invoice_id'] = invoice_map[row['invoice_id']]
        item = payment_items.get((row['payment_id'], row['invoice_id']))
        if not item or row['amount'] != item['amount']:
            raise ValueError('A reservation does not match its payment snapshot.')
        groups.setdefault(row['payment_id'], []).append(item)
    for row in rows['reservations']:
        if row['mssv'] is not None:
            if row['mssv'] not in code_map:
                raise ValueError('A reservation refers to an unknown student.')
            row['mssv'] = code_map[row['mssv']]
        items = groups.get(row['payment_id'], [])
        if items:
            row['request_hash'] = fingerprint({'mssv': row['mssv'],
                'items': sorted((item['invoice_id'], item['invoice_version']) for item in items),
                'total': format(row['total_amount'], '.2f')})
    return {'rows': rows, 'student_ids': student_map, 'invoice_ids': invoice_map, 'mssvs': code_map}


def read_snapshot(connection):
    return {key: [dict(row) for row in connection.exec_driver_sql(
        f'SELECT * FROM {table} WITH (TABLOCKX, HOLDLOCK)').mappings()] for key, table in TABLES.items()}


def insert_identity_rows(connection, table, rows):
    if not rows:
        return
    columns = list(rows[0])
    statement = text(f"INSERT INTO {table} ({','.join('[' + key + ']' for key in columns)}) "
                     f"VALUES ({','.join(':' + key for key in columns)})")
    connection.exec_driver_sql(f'SET IDENTITY_INSERT {table} ON')
    try:
        connection.execute(statement, rows)
    finally:
        connection.exec_driver_sql(f'SET IDENTITY_INSERT {table} OFF')


def rewrite(connection, plan):
    rows = plan['rows']
    # Do not disable constraints. Delete/reinsert in FK order inside one transaction.
    for key in ('reservation_items', 'invoices', 'students'):
        connection.exec_driver_sql('DELETE FROM ' + TABLES[key])
    for key in ('students', 'invoices', 'reservation_items'):
        insert_identity_rows(connection, TABLES[key], rows[key])
    # Temporary negative references avoid transient UNIQUE(payment_id, invoice_id)
    # collisions when an old ID happens to equal another invoice's new ID.
    connection.exec_driver_sql('UPDATE payment_db.dbo.payment_items SET invoice_id = -invoice_id')
    for row in rows['payment_items']:
        connection.execute(text('UPDATE payment_db.dbo.payment_items SET invoice_id=:invoice_id, '
            'semester=:semester WHERE id=:id'), {key: row[key] for key in ('id', 'invoice_id', 'semester')})
    for row in rows['payments']:
        connection.execute(text('UPDATE payment_db.dbo.payments SET mssv=:mssv, student_name=:student_name, '
            'request_hash=:request_hash WHERE payment_id=:payment_id'),
            {key: row[key] for key in ('payment_id', 'mssv', 'student_name', 'request_hash')})
    for row in rows['reservations']:
        connection.execute(text('UPDATE dbo.tuition_reservations SET mssv=:mssv, request_hash=:request_hash '
            'WHERE payment_id=:payment_id'), {key: row[key] for key in ('payment_id', 'mssv', 'request_hash')})
    for key in ('students', 'invoices', 'reservation_items'):
        last_id = max((row['id'] for row in rows[key]), default=0)
        connection.exec_driver_sql(f"DBCC CHECKIDENT ('{TABLES[key]}', RESEED, {last_id}) WITH NO_INFOMSGS")
    actual = read_snapshot(connection)
    for key in TABLES:
        primary_key = 'payment_id' if key in ('payments', 'reservations') else 'id'
        order = lambda row: row[primary_key]
        if sorted(actual[key], key=order) != sorted(rows[key], key=order):
            raise RuntimeError('Post-rewrite verification failed; the transaction will roll back.')


def backup_databases(databases=('tuition_db', 'payment_db'), *, operation='normalize'):
    if not databases or any(name not in {'account_db', 'payment_db', 'tuition_db'} for name in databases):
        raise ValueError('Backups are limited to the local application databases.')
    if operation not in {'normalize', 'account-ids'}:
        raise ValueError('Unknown database backup operation.')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:8]
    files = {}
    engine = create_engine(sqlserver_url('master'), isolation_level='AUTOCOMMIT')
    try:
        with engine.connect() as connection:
            cursor = connection.connection.driver_connection.cursor()
            try:
                for database in databases:
                    path = f'/var/opt/mssql/data/{database}-before-{operation}-{stamp}.bak'
                    # BACKUP/RESTORE emit multiple ODBC result sets. Drain all of
                    # them so closing a result cannot cancel an unfinished backup.
                    for statement in (
                        f"BACKUP DATABASE [{database}] TO DISK = N'{path}' WITH COPY_ONLY, CHECKSUM, INIT",
                        f"RESTORE VERIFYONLY FROM DISK = N'{path}' WITH CHECKSUM",
                    ):
                        cursor.execute(statement)
                        while cursor.nextset():
                            pass
                    files[database] = path
            finally:
                cursor.close()
    finally:
        engine.dispose()
    return files


def normalize(confirmation):
    require_local_docker()
    if confirmation != 'ibanking-demo':
        raise ValueError('Normalize requires the exact confirmation token ibanking-demo and stopped APIs.')
    engine = create_engine(sqlserver_url('tuition_db'))
    try:
        # Validate before creating backups and again under locks before writing.
        with engine.begin() as connection:
            build_plan(read_snapshot(connection))
        backups = backup_databases()
        from services.tuition.migrate import disable_identity_cache
        with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
            disable_identity_cache(connection)
        with engine.begin() as connection:
            connection.exec_driver_sql('SET XACT_ABORT ON')
            plan = build_plan(read_snapshot(connection))
            rewrite(connection, plan)
        return {'status': 'NORMALIZED', 'backups': backups,
            'student_count': len(plan['rows']['students']), 'invoice_count': len(plan['rows']['invoices']),
            'students': plan['rows']['students'],
            'student_id_map': plan['student_ids'], 'invoice_id_map': plan['invoice_ids'], 'mssv_map': plan['mssvs']}
    finally:
        engine.dispose()
