"""Export the running demo's schemas for offline review (no credentials needed)."""
import json
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

root = Path(__file__).resolve().parents[1]
output = root / 'docs/api'
output.mkdir(exist_ok=True)
client = build_opener(ProxyHandler({}))
for name, port in [('account',8001),('payment',8002),('tuition',8003)]:
    with client.open(f'http://127.0.0.1:{port}/openapi.json',timeout=10) as response:
        schema = json.load(response)
    assert schema['openapi'].startswith('3.') and schema['paths']
    (output / f'openapi-{name}.json').write_text(json.dumps(schema,ensure_ascii=False,indent=2),encoding='utf8')
    print(f'{name}: {len(schema["paths"])} API paths exported')
