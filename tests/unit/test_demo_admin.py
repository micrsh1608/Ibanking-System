import pytest
from pydantic import ValidationError

from infra.docker import demo_admin, init_databases


@pytest.mark.parametrize('mode,seeded', [(None,False),('false',False),('true',True)])
def test_bootstrap_only_seeds_when_explicitly_enabled(monkeypatch, mode, seeded):
    calls=[]
    monkeypatch.delenv('IBANKING_SEED_DEMO',raising=False)
    if mode is not None:monkeypatch.setenv('IBANKING_SEED_DEMO',mode)
    monkeypatch.setattr(init_databases,'prepare_schema',lambda:calls.append('schema'))
    monkeypatch.setattr(init_databases,'seed_demo',lambda:calls.append('seed'))
    init_databases.main()
    assert calls==(['schema','seed'] if seeded else ['schema'])


@pytest.mark.parametrize('server',['HUY-PC','127.0.0.1,14330','sqlserver,1433;DATABASE=master'])
def test_reset_refuses_non_docker_targets_before_opening_connection(monkeypatch, server):
    monkeypatch.setenv('DB_SERVER',server)
    monkeypatch.setattr(demo_admin,'create_engine',lambda *a,**kw:pytest.fail('must not connect'))
    with pytest.raises(RuntimeError):demo_admin.reset_databases('ibanking-demo')


def test_reset_requires_explicit_confirmation_before_opening_connection(monkeypatch):
    for key,value in {'DB_SERVER':'sqlserver,1433','DB_NAME':'account_db','PAYMENT_DB_NAME':'payment_db','TUITION_DB_NAME':'tuition_db'}.items():monkeypatch.setenv(key,value)
    for key in ('ACCOUNT_DATABASE_URL','PAYMENT_DATABASE_URL','TUITION_DATABASE_URL'):monkeypatch.delenv(key,raising=False)
    monkeypatch.setattr(demo_admin,'create_engine',lambda *a,**kw:pytest.fail('must not connect'))
    with pytest.raises(ValueError):demo_admin.reset_databases('not-confirmed')


@pytest.mark.parametrize('change',[{'amount':'0'},{'amount':'-1'},{'amount':'1.001'},{'amount':'10000000000000000'},
    {'mssv':'bad; DROP TABLE students'},{'student_name':'  '},{'semester':'x'*33}])
def test_new_demo_tuition_rejects_invalid_values(change):
    with pytest.raises(ValidationError):
        demo_admin.NewTuition(**(dict(mssv='SV2026002',student_name='Nguyễn Văn An',semester='TEST-HK1',amount='1500000.00')|change))


def test_create_test_payer_refuses_non_local_configuration_before_provisioning(monkeypatch):
    from services.account import seed
    monkeypatch.setenv('DB_SERVER', 'production.invalid')
    monkeypatch.setattr(seed, 'create_test_account', lambda **kwargs: pytest.fail('must not provision'))
    with pytest.raises(RuntimeError):
        demo_admin.create_test_account('huy2', 'second@example.org')
