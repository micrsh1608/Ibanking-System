"""Build a source/document backup with a positive file allowlist and secret check."""
import hashlib
import io
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'submission'
OUT.mkdir(exist_ok=True)
release=json.loads((ROOT/'artifacts/release-acceptance-latest.json').read_text(encoding='utf8'))
backend=json.loads((ROOT/'artifacts/backend-acceptance.json').read_text(encoding='utf8'))
browser=json.loads((ROOT/'artifacts/browser-acceptance.json').read_text(encoding='utf8'))
assert release['status']=='PASS' and release['clean_image_build'] is True
assert len(backend['checks'])==8 and all(c['result']=='PASS' for c in backend['checks'])
assert browser['stats']['expected']==4 and browser['stats']['unexpected']==0 and browser['stats']['flaky']==0

root_files=['README.md','.env.example','.gitignore','.dockerignore','compose.yaml','start.ps1','main.py','requirements.txt','requirements-dev.txt','package.json','package-lock.json','playwright.config.cjs','pytest.ini']
files=[ROOT/name for name in root_files]
blocked={'.git','.venv','venv','__pycache__','node_modules','.pytest_cache','.codex','.agents'}
for directory in ['services','shared','frontend','infra','scripts','docs','tests']:
    for file in (ROOT/directory).rglob('*'):
        if file.is_file() and not blocked.intersection(file.relative_to(ROOT).parts) and file.suffix.lower() not in {'.pyc','.pyo','.log','.env','.bak','.mdf','.ldf'} and not file.name.startswith('.env'):
            files.append(file)
for name in ['README.md','bao-cao-ibanking.pdf','bao-cao-ibanking.md','trinh-bay-ibanking-v2.pptx']:
    file=OUT/name
    assert file.exists(), f'Missing final output: {name}'
    files.append(file)
evidence=['artifacts/backend-acceptance.json','artifacts/browser-acceptance.json','artifacts/release-acceptance-latest.json']
evidence += ['artifacts/'+name for name in ['payment-success-desktop.png','payment-history-desktop.png','payment-selection-mobile.png','payment-success-mobile.png']]
files += [ROOT/name for name in evidence]
files.append(ROOT/'artifacts/release'/release['run_id']/'acceptance.json')

# Check actual private configuration values without including or displaying them.
private_values=[]
for config in [ROOT/'.env',ROOT/'infra/env/docker.env']:
    if config.exists():
        for line in config.read_text(encoding='utf-8-sig').splitlines():
            if line.strip() and not line.lstrip().startswith('#') and '=' in line:
                key,value=line.split('=',1); value=value.strip().strip('"\'')
                if re.search(r'(SECRET|PASSWORD|KEY)$',key.strip()) and len(value)>=8:
                    private_values.append((key.strip(),value.encode('utf8')))

entries={}
for file in sorted(set(files)):
    relative=file.relative_to(ROOT).as_posix()
    assert not file.is_symlink(), 'Refusing a symlink in backup: '+relative
    assert relative not in {'.env','infra/env/docker.env'}
    data=file.read_bytes()
    payloads=[data]
    if file.suffix=='.pptx':
        with ZipFile(io.BytesIO(data)) as deck:
            payloads += [deck.read(name) for name in deck.namelist() if name.endswith('.xml')]
    for key,value in private_values:
        assert not any(value in payload for payload in payloads), f'Private configuration value ({key}) found in {relative}; backup not published'
    entries[relative]=data

manifest={'created_at_utc':datetime.now(timezone.utc).isoformat(),'release_run':release['run_id'],'release_image_id':release['image_id'],
    'excludes':['private .env files','.git','.venv','node_modules','SQL data','raw logs','Docker images'],
    'files':[{'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()} for name,data in entries.items()]}
manifest_bytes=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf8')
(OUT/'SOURCE-MANIFEST.json').write_bytes(manifest_bytes)
archive=OUT/'ibanking-source.zip'
with ZipFile(archive,'w',compression=ZIP_DEFLATED,compresslevel=9) as zipfile:
    for name,data in entries.items():
        zipfile.writestr('Ibanking-System/'+name,data)
    zipfile.writestr('Ibanking-System/submission/SOURCE-MANIFEST.json',manifest_bytes)
with ZipFile(archive) as zipfile:
    assert zipfile.testzip() is None
    assert not any(name.endswith('/.env') or name.endswith('/docker.env') or '/node_modules/' in name for name in zipfile.namelist())
    for row in manifest['files']:
        assert hashlib.sha256(zipfile.read('Ibanking-System/'+row['path'])).hexdigest()==row['sha256']
for name in evidence:
    dest=OUT/'evidence'/Path(name).name
    dest.parent.mkdir(exist_ok=True)
    shutil.copyfile(ROOT/name,dest)
delivered=[archive,OUT/'bao-cao-ibanking.pdf',OUT/'bao-cao-ibanking.md',OUT/'trinh-bay-ibanking-v2.pptx',OUT/'SOURCE-MANIFEST.json']
(OUT/'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(file.read_bytes()).hexdigest()+'  '+file.name+'\n' for file in delivered),encoding='utf8')
print(json.dumps({'archive':str(archive),'source_files':len(entries),'bytes':archive.stat().st_size,'private_config_scan':'PASS','archive_readback_hashes':'PASS'},ensure_ascii=False))
