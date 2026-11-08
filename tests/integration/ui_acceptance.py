"""Browser-only acceptance on an isolated SQL/Mailpit stack; preserves full-release evidence."""
import json
import os
import subprocess

from tests.integration import release_acceptance as r


def main():
    report={'status':'RUNNING','project':r.PROJECT,'profile':'isolated','scope':'browser and UI cache fixes'}
    try:
        print('Isolated UI acceptance: '+r.PROJECT,flush=True)
        r.command(['build','db-init'],name='ui-image-build')
        r.command(['up','--no-build','--wait','--wait-timeout','300'],name='ui-start')
        r.wait_for(r.healthy)
        env=os.environ.copy();env['IBANKING_E2E_BASE_URL']='http://127.0.0.1:8101'
        result=subprocess.run(['npm.cmd' if os.name=='nt' else 'npm','run','test:e2e'],cwd=r.ROOT,env=env,capture_output=True,text=True,encoding='utf8',errors='replace')
        (r.OUTPUT/'ui-browser-checks.log').write_text(result.stdout+'\n'+result.stderr,encoding='utf8')
        if result.returncode:raise RuntimeError('Browser checks failed: '+str(r.OUTPUT/'ui-browser-checks.log'))
        stats=json.loads((r.ROOT/'artifacts/browser-acceptance.json').read_text(encoding='utf8'))['stats']
        assert stats['expected']>=26 and not stats['unexpected'] and not stats['flaky']
        report.update(status='PASS',browser_tests=stats['expected'])
        print('PASS: '+str(stats['expected'])+' isolated browser tests',flush=True)
    except Exception as error:
        report.update(status='FAIL',error=str(error))
        raise
    finally:
        r.command(['down','--timeout','20'],name='ui-teardown',check=False)
        (r.ROOT/'artifacts/ui-acceptance-latest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')


if __name__=='__main__':main()
