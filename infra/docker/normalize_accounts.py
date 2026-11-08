"""Offline local-demo ID rewrite, preserving money and persisted references.

Run only through demo-data.ps1 -NormalizeAccounts with the APIs stopped.
Account and Payment are backed up before any data changes. Existing JWTs of
users whose IDs change must be replaced by signing in again.
"""
import json
import hashlib

from sqlalchemy import create_engine, text

from infra.docker.demo_admin import require_local_docker
from infra.docker.normalize_tuition import backup_databases, insert_identity_rows
from shared.database import sqlserver_url


TABLES = {
    'users': 'dbo.users', 'accounts': 'dbo.accounts',
    'entries': 'dbo.account_entries', 'cancellations': 'dbo.account_cancellations',
    'payments': 'payment_db.dbo.payments',
}


def build_plan(snapshot):
    rows = {key: [dict(row) for row in values] for key, values in snapshot.items()}
    if not rows['users'] or not rows['accounts']:
        raise ValueError('No users/accounts to normalize.')
    user_ids = {row['id']: new_id for new_id, row in enumerate(sorted(rows['users'], key=lambda row: row['id']), 1)}
    account_ids = {row['id']: new_id for new_id, row in enumerate(sorted(rows['accounts'], key=lambda row: row['id']), 1)}
    owners = {row['id']: row['user_id'] for row in rows['accounts']}

    for row in rows['users']:
        old_id = row['id']
        if user_ids[old_id] != old_id and row.get('email_code_hash'):
            raise ValueError('Finish or cancel the pending email proof of a remapped user first.')
        row['id'] = user_ids[old_id]
    for row in rows['accounts']:
        if row['user_id'] not in user_ids:
            raise ValueError('An account has no matching user; nothing was rewritten.')
        row['id'], row['user_id'] = account_ids[row['id']], user_ids[row['user_id']]
    for row in rows['entries']:
        if row['account_id'] not in account_ids:
            raise ValueError('A ledger entry refers to an unknown account.')
        row['account_id'] = account_ids[row['account_id']]
    for row in rows['cancellations'] + rows['payments']:
        old_account, old_user = row['account_id'], row['payer_user_id']
        if old_account not in account_ids or old_user not in user_ids or owners[old_account] != old_user:
            raise ValueError('A payment/cancellation does not match its account owner.')
        row['account_id'], row['payer_user_id'] = account_ids[old_account], user_ids[old_user]
    for row in rows['payments']:
        original = next(old for old in snapshot['payments'] if old['payment_id'] == row['payment_id'])
        changed = (row['payer_user_id'], row['account_id']) != (original['payer_user_id'], original['account_id'])
        if changed and row['status'] not in {'SUCCEEDED', 'FAILED', 'REFUNDED'}:
            raise ValueError('Finish or cancel pending payments of a remapped account first.')
        if changed:
            payload = {'user_id': row['payer_user_id'], 'mssv': row['mssv'],
                'selection_mode': row['selection_mode'], 'invoice_ids': []}
            row['request_hash'] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return {'rows': rows, 'user_ids': user_ids, 'account_ids': account_ids}


def read_snapshot(connection):
    return {key: [dict(row) for row in connection.exec_driver_sql(
        f'SELECT * FROM {table} WITH (TABLOCKX, HOLDLOCK)').mappings()] for key, table in TABLES.items()}


def rewrite(connection, plan):
    rows = plan['rows']
    # FK constraints stay enabled throughout the cross-database transaction.
    for key in ('cancellations', 'entries', 'accounts', 'users'):
        connection.exec_driver_sql('DELETE FROM ' + TABLES[key])
    for key in ('users', 'accounts', 'entries'):
        insert_identity_rows(connection, TABLES[key], rows[key])
    if rows['cancellations']:
        connection.execute(text('INSERT INTO dbo.account_cancellations '
            '(payment_id,account_id,payer_user_id,amount,created_at) '
            'VALUES (:payment_id,:account_id,:payer_user_id,:amount,:created_at)'), rows['cancellations'])
    for row in rows['payments']:
        connection.execute(text('UPDATE payment_db.dbo.payments SET payer_user_id=:payer_user_id, '
            'account_id=:account_id,request_hash=:request_hash WHERE payment_id=:payment_id'),
            {key: row[key] for key in ('payment_id', 'payer_user_id', 'account_id', 'request_hash')})
    for key in ('users', 'accounts', 'entries'):
        if rows[key]:
            maximum = max(row['id'] for row in rows[key])
            connection.exec_driver_sql(f"DBCC CHECKIDENT ('{TABLES[key]}', RESEED, {maximum}) WITH NO_INFOMSGS")
    actual = read_snapshot(connection)
    for key in TABLES:
        primary_key = 'payment_id' if key in ('payments', 'cancellations') else 'id'
        order = lambda row: row[primary_key]
        if sorted(actual[key], key=order) != sorted(rows[key], key=order):
            raise RuntimeError('Account ID verification failed; the transaction will roll back.')


def normalize(confirmation):
    require_local_docker()
    if confirmation != 'ibanking-demo':
        raise ValueError('Account normalization requires ibanking-demo confirmation and stopped APIs.')
    engine = create_engine(sqlserver_url('account_db'))
    try:
        with engine.begin() as connection:
            build_plan(read_snapshot(connection))
        backups = backup_databases(('account_db', 'payment_db'), operation='account-ids')
        from services.account.migrate import disable_identity_cache
        with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
            disable_identity_cache(connection)
        with engine.begin() as connection:
            connection.exec_driver_sql('SET XACT_ABORT ON')
            plan = build_plan(read_snapshot(connection))
            rewrite(connection, plan)
        return {'status': 'NORMALIZED', 'backups': backups,
            'user_id_map': plan['user_ids'], 'account_id_map': plan['account_ids'],
            'users': [{'id': row['id'], 'username': row['username']} for row in plan['rows']['users']],
            'accounts': [{'id': row['id'], 'user_id': row['user_id'], 'account_number': row['account_number'],
                'balance': format(row['balance'], '.2f')} for row in plan['rows']['accounts']],
            'payment_count': len(plan['rows']['payments']),
            'note': 'Existing balances, hashes, verified profiles and payment outcomes were preserved. Remapped users must sign in again.'}
    finally:
        engine.dispose()
