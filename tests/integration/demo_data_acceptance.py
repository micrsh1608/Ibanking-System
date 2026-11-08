"""Reset/seed acceptance on fresh isolated Docker volumes, with Mailpit only."""
import json
import subprocess
from sqlalchemy import text

from tests.integration import release_acceptance as r


def admin(*args):
    return r.command(['run','--rm','--no-deps','db-init','python','-m','infra.docker.demo_admin',*args])


def empty(data):
    return all(count==0 for tables in data.values() for name,count in tables.items() if name!='schema_revisions')


def main():
    checks=[]
    def passed(name):checks.append({'name':name,'result':'PASS'});print('PASS:',name,flush=True)
    report={'project':r.PROJECT,'profile':'isolated','checks':checks,'status':'RUNNING'}
    try:
        print('Isolated demo data test: '+r.PROJECT,flush=True)
        r.command(['build','db-init'],name='demo-admin-build')
        r.command(['up','--no-build','--wait','--wait-timeout','300'],name='demo-admin-start')
        r.wait_for(r.healthy)
        with r.a.PaymentSession.begin() as db:
            db.execute(text('CREATE TABLE legacy_demo_rows (id INTEGER PRIMARY KEY)'))
            db.execute(text('INSERT INTO legacy_demo_rows VALUES (1)'))
        r.command(['stop','account','payment','tuition'])
        clean=json.loads(admin('reset','--confirm-local-reset','ibanking-demo'))
        assert empty(clean) and 'legacy_demo_rows' not in clean['payment_db']
        passed('Reset drops legacy data and leaves every business table empty in all three databases')
        r.command(['run','--rm','--no-deps','-e','IBANKING_SEED_DEMO=false','db-init'])
        assert empty(json.loads(admin('status')))
        passed('Normal schema-only bootstrap does not silently repopulate empty databases')
        admin('seed');seeded=json.loads(admin('status'))
        assert seeded['account_db']['users']==seeded['account_db']['accounts']==seeded['tuition_db']['students']==1
        assert seeded['tuition_db']['tuition_invoices']==2 and seeded['payment_db']['payments']==0
        admin('seed');assert json.loads(admin('status'))==seeded
        passed('Explicit demo seed creates one user/account/student and two invoices, and is repeatable')
        command=['add-tuition','--mssv','SV2026002','--student-name','Nguyen Van An','--semester','TEST-HK1','--amount','1500000.00']
        invoice=json.loads(admin(*command));assert invoice['amount']=='1500000.00' and invoice['status']=='UNPAID'
        duplicate=subprocess.run(r.a.COMPOSE+['run','--rm','--no-deps','db-init','python','-m','infra.docker.demo_admin',*command],capture_output=True)
        assert duplicate.returncode!=0
        assert json.loads(admin('status'))['tuition_db']['tuition_invoices']==3
        passed('New tuition can be created without overwriting a duplicate semester')
        r.command(['up','--detach','--no-deps','--no-build','--wait','account','payment','tuition'])
        token=r.a.check(r.a.request('account','POST','/auth/login',body={'username':'huy','password':'HuyDemo_123!'}))['access_token']
        headers={'Authorization':'Bearer '+token}
        assert r.a.check(r.a.request('account','GET','/accounts/me',headers=headers))['balance']=='10000000.00'
        assert r.a.check(r.a.request('tuition','GET','/api/v1/tuition/SV20261013',headers=headers))['total_unpaid']=='5000000.00'
        assert r.a.check(r.a.request('payment','GET','/api/v1/payments',headers=headers))['items']==[]
        passed('Explicitly seeded data supports login, correct balance/tuition lookup and empty history')
        r.command(['stop','account','payment','tuition'])
        assert empty(json.loads(admin('reset','--confirm-local-reset','ibanking-demo')))
        passed('Reset can be repeated after seeding and leaves a blank demo again')
        report['status']='PASS'
    except Exception:
        report['status']='FAIL'
        raise
    finally:
        r.command(['down','--timeout','20'],name='demo-admin-teardown',check=False)
        (r.ROOT/'artifacts/demo-data-acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')


if __name__=='__main__':main()
