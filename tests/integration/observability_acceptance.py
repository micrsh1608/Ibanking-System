"""Prove one correlation ID crosses the real gateway and all three services."""
import json
import subprocess
from uuid import UUID, uuid4

from tests.integration import backend_acceptance as a


def main():
    if a.PROFILE != 'isolated':
        raise RuntimeError('Run tracing acceptance only through the isolated release runner.')
    user = a.new_user()
    mssv, _ = a.new_student(['400000.00', '600000.00'])
    key, request_id = str(uuid4()), str(uuid4())
    response = a.request('account', 'POST', '/api/v1/payments', headers=user['headers'] | {
        'Idempotency-Key': key, 'X-Request-ID': request_id},
        body={'mssv': mssv, 'selection_mode': 'ALL_UNPAID', 'terms_accepted': True})
    assert response.status_code == 201, response.text
    assert response.headers['X-Request-ID'] == request_id
    result = subprocess.run(a.COMPOSE + ['logs', '--no-color', '--no-log-prefix', 'account', 'payment', 'tuition'],
        cwd=a.ROOT, capture_output=True, text=True, encoding='utf-8', check=True)
    records=[]
    for line in (result.stdout+'\n'+result.stderr).splitlines():
        try:
            item=json.loads(line)
        except ValueError:
            continue
        if isinstance(item,dict) and item.get('request_id')==request_id:
            records.append(item)
    assert {record['service'] for record in records}=={'account','payment','tuition'}
    assert all('route' in record and 'duration_ms' in record for record in records)
    joined=json.dumps(records)
    assert mssv not in joined and user['headers']['Authorization'] not in joined
    invalid = a.request('account','GET','/health',headers={'X-Request-ID':'invalid-request-id'})
    UUID(invalid.headers['X-Request-ID'])
    assert invalid.headers['X-Request-ID']!='invalid-request-id'
    report={'status':'PASS','profile':'isolated','project':a.project,
        'checks':['Gateway and all three services share one request ID',
                  'Structured logs use route templates without MSSV or bearer token',
                  'Invalid incoming IDs are replaced with a server-generated UUID'],
        'request_id':request_id,'services':sorted({record['service'] for record in records}),
        'records':records}
    (a.ROOT/'artifacts/observability-acceptance.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('PASS: real three-service request correlation and safe structured logs',flush=True)


if __name__=='__main__':main()
