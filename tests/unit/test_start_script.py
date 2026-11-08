"""Exercise the Windows launcher without Docker, networks or the real demo DB."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


POWERSHELL = shutil.which('powershell')
ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(not POWERSHELL, reason='Windows PowerShell required')


def launch(tmp_path, scenario='matching', *options):
    workspace = tmp_path / 'demo with spaces'
    workspace.mkdir()
    shutil.copyfile(ROOT / 'start.ps1', workspace / 'start.ps1')
    for directory in ('infra/env', 'services', 'shared', 'frontend'):
        (workspace / directory).mkdir(parents=True, exist_ok=True)
    (workspace / 'requirements.txt').write_text('fastapi\n')
    config = workspace / 'infra/env/docker.env'
    config.write_text('# keep this private configuration unchanged\n')
    commands = tmp_path / 'commands.jsonl'
    harness = tmp_path / 'docker-stub.ps1'
    harness.write_text(r'''
function global:docker {
    $arguments = @($args)
    $record = @{args=$arguments; seed=$env:IBANKING_SEED_DEMO} | ConvertTo-Json -Compress
    [IO.File]::AppendAllText($env:STARTUP_TEST_LOG, $record + "`n")
    $global:LASTEXITCODE = 0
    if ($arguments[0] -eq 'info') { 'linux'; return }
    if ($arguments[0] -eq 'image') {
        if ($env:STARTUP_TEST_SCENARIO -eq 'missing-app' -and $arguments[-1] -eq 'ibanking-api:local') { return }
        if ($env:STARTUP_TEST_SCENARIO -eq 'missing-sql' -and $arguments[-1] -like 'mcr.microsoft.com/*') { return }
        'local-image-id'; return
    }
    if ($arguments[0] -eq 'run') {
        $input | Out-Null
        if ($env:STARTUP_TEST_SCENARIO -in @('changed', 'build-fails')) { $global:LASTEXITCODE = 3 }
        return
    }
    if ($arguments -contains 'build' -and $env:STARTUP_TEST_SCENARIO -eq 'build-fails') {
        $global:LASTEXITCODE = 1; return
    }
    if ($arguments -contains 'up' -and $env:STARTUP_TEST_SCENARIO -eq 'startup-fails') {
        $global:LASTEXITCODE = 1; return
    }
    if ($arguments -contains 'port') {
        if ($env:STARTUP_TEST_SCENARIO -eq 'wrong-sql-port') { '127.0.0.1:14331'; return }
        '127.0.0.1:14330'; return
    }
    if ($arguments -contains 'exec') {
        if ($env:STARTUP_TEST_SCENARIO -eq 'catalog-fails') {
            '{"status":"ERROR","error":"Catalog unavailable; existing data preserved."}'
            $global:LASTEXITCODE = 1; return
        }
        $users = @(1..10 | ForEach-Object {
            @{username=('demo{0:D2}' -f $_);account_id=$_;balance='10000000.00';
              email='';email_channel='smtp';email_verified=$false;verification='manual_on_profile'}
        })
        if ($env:STARTUP_TEST_SCENARIO -eq 'bad-catalog-metadata') { $users[0].account_id='1); DROP TABLE accounts' }
        $students = @(1..12 | ForEach-Object {
            @{id=$_;mssv=('SV2026{0}' -f (1000+$_));student_name=('Student '+$_);unpaid_total='1000000.00'}
        })
        @{status='PREPARED';users=$users;students=$students;manual_verification_required=10} |
            ConvertTo-Json -Depth 5 -Compress
        return
    }
    if ($arguments -contains 'version') { '5.1.3' }
}
& (Join-Path $env:STARTUP_TEST_ROOT 'start.ps1') @args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
''', encoding='utf-8-sig')
    result = subprocess.run(
        [POWERSHELL, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(harness), *options],
        env=os.environ | {'STARTUP_TEST_ROOT': str(workspace), 'STARTUP_TEST_LOG': str(commands),
                          'STARTUP_TEST_SCENARIO': scenario},
        capture_output=True, text=True, timeout=30,
    )
    assert config.read_text() == '# keep this private configuration unchanged\n'
    calls = [json.loads(line) for line in commands.read_text(encoding='utf-8-sig').splitlines()]
    return result, calls


def commands_with(calls, token):
    return [call['args'] for call in calls if token in call['args']]


def test_matching_image_starts_without_build_or_registry(tmp_path):
    result, calls = launch(tmp_path, 'matching', '-Detached')
    assert result.returncode == 0, result.stdout + result.stderr
    assert not commands_with(calls, 'build')
    assert not commands_with(calls, 'pull')
    assert not commands_with(calls, 'stop')
    assert not commands_with(calls, 'exec')
    probe = commands_with(calls, 'run')[0]
    assert probe[probe.index('--network') + 1] == 'none'
    up = commands_with(calls, 'up')[0]
    assert '--no-build' in up and '--wait' in up
    assert up[up.index('--pull') + 1] == 'never'
    assert all(call['seed'] == 'false' for call in calls)


@pytest.mark.parametrize('scenario', ['changed', 'missing-app'])
def test_missing_or_changed_application_builds_once_before_start(tmp_path, scenario):
    result, calls = launch(tmp_path, scenario, '-Detached')
    assert result.returncode == 0, result.stdout + result.stderr
    build = commands_with(calls, 'build')
    assert len(build) == 1 and build[0][-2:] == ['build', 'account']
    assert calls.index(next(c for c in calls if 'build' in c['args'])) < calls.index(next(c for c in calls if 'up' in c['args']))


def test_rebuild_is_explicit_and_preserves_seed_option(tmp_path):
    result, calls = launch(tmp_path, 'matching', '-Rebuild', '-SeedDemo', '-Detached')
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(commands_with(calls, 'build')) == 1
    assert not commands_with(calls, 'run')
    assert all(call['seed'] == 'true' for call in calls)


def test_only_missing_infrastructure_image_is_pulled(tmp_path):
    result, calls = launch(tmp_path, 'missing-sql', '-Detached')
    assert result.returncode == 0, result.stdout + result.stderr
    assert commands_with(calls, 'pull') == [['pull', 'mcr.microsoft.com/mssql/server:2022-latest']]


def test_failed_build_never_stops_existing_sql_or_services(tmp_path):
    result, calls = launch(tmp_path, 'build-fails')
    assert result.returncode == 1
    assert 'Existing services and data were left in place' in result.stdout
    assert not commands_with(calls, 'up')
    assert not commands_with(calls, 'stop')


@pytest.mark.parametrize('options', [(), ('-Detached',), ('-PrepareDemo', '-Detached')])
def test_failed_startup_keeps_containers_for_diagnosis(tmp_path, options):
    result, calls = launch(tmp_path, 'startup-fails', *options)
    assert result.returncode == 1
    assert not commands_with(calls, 'stop')
    assert not commands_with(calls, 'logs')
    assert not commands_with(calls, 'exec')


def test_foreground_only_stops_after_successful_start_and_log_session(tmp_path):
    result, calls = launch(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    actions = [token for call in calls for token in call['args'] if token in ('up', 'logs', 'stop')]
    assert actions == ['up', 'logs', 'stop']


@pytest.mark.parametrize('options', [(), ('-PrepareDemo',)])
def test_check_does_not_build_pull_or_start_containers(tmp_path, options):
    result, calls = launch(tmp_path, 'matching', '-Check', *options)
    assert result.returncode == 0, result.stdout + result.stderr
    assert all(call['args'][0] != 'image' for call in calls)
    for action in ('run', 'build', 'pull', 'up', 'stop', 'exec'):
        assert not commands_with(calls, action)


def test_prepare_demo_waits_for_services_then_exports_catalog_and_read_only_sql(tmp_path):
    result, calls = launch(tmp_path, 'matching', '-PrepareDemo', '-Detached')
    assert result.returncode == 0, result.stdout + result.stderr
    actions = [token for call in calls for token in call['args'] if token in ('up', 'port', 'exec')]
    assert actions == ['up', 'port', 'exec']
    helper = commands_with(calls, 'exec')[0]
    assert helper[-3:] == ['python', '-m', 'infra.docker.demo_catalog']
    assert 'IBANKING_DEMO_CATALOG_TARGET=ibanking-demo' in helper
    directory = tmp_path / 'demo with spaces' / 'artifacts'
    catalog = json.loads((directory / 'demo-accounts.json').read_text(encoding='utf-8'))
    assert len(catalog['users']) == 10 and len(catalog['students']) == 12
    sql = (directory / 'demo-inspect.sql').read_text(encoding='utf-8')
    assert 'WHERE a.id IN (1,2,3,4,5,6,7,8,9,10)' in sql
    assert 'SV20261001' in sql and 'SV20261012' in sql
    assert not any(word in sql.upper().split() for word in ('DELETE', 'INSERT', 'UPDATE', 'DROP'))
    assert all(call['seed'] == 'false' for call in calls)
    assert not commands_with(calls, 'stop')


def test_prepare_demo_finishes_before_foreground_log_session(tmp_path):
    result, calls = launch(tmp_path, 'matching', '-PrepareDemo')
    assert result.returncode == 0, result.stdout + result.stderr
    actions = [token for call in calls for token in call['args'] if token in ('up', 'exec', 'logs', 'stop')]
    assert actions == ['up', 'exec', 'logs', 'stop']


def test_failed_catalog_keeps_running_services_and_does_not_publish_artifacts(tmp_path):
    result, calls = launch(tmp_path, 'catalog-fails', '-PrepareDemo', '-Detached')
    assert result.returncode == 1
    assert 'Catalog unavailable' in result.stdout
    assert not commands_with(calls, 'stop') and not commands_with(calls, 'logs')
    assert not (tmp_path / 'demo with spaces' / 'artifacts' / 'demo-accounts.json').exists()


def test_prepare_demo_refuses_an_unexpected_sql_endpoint_before_seeding(tmp_path):
    result, calls = launch(tmp_path, 'wrong-sql-port', '-PrepareDemo', '-Detached')
    assert result.returncode == 1
    assert 'Expected the main SQL endpoint' in result.stdout
    assert not commands_with(calls, 'exec') and not commands_with(calls, 'stop')


def test_invalid_catalog_metadata_is_not_published_as_a_sql_script(tmp_path):
    result, calls = launch(tmp_path, 'bad-catalog-metadata', '-PrepareDemo', '-Detached')
    assert result.returncode == 1
    assert 'Invalid catalog account metadata' in result.stdout
    directory = tmp_path / 'demo with spaces' / 'artifacts'
    assert not (directory / 'demo-accounts.json').exists()
    assert not (directory / 'demo-inspect.sql').exists()
    assert not commands_with(calls, 'stop')
