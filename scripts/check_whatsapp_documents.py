"""Exercise generic documents and activate the local receiver after successful checks."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import urlopen

root = Path(__file__).resolve().parents[1]
folder = root / 'reports/whatsapp-documents-20261026'
unit = 'nienfos-whatsapp-ingest.service'
env = {**os.environ, 'XDG_RUNTIME_DIR': f'/run/user/{os.getuid()}', 'DBUS_SESSION_BUS_ADDRESS': f'unix:path=/run/user/{os.getuid()}/bus'}
def ctl(*args):
    return subprocess.check_output(['systemctl', '--user', *args], env=env, text=True).strip()
pid_before = ctl('show', unit, '-p', 'MainPID', '--value')
node = str(Path(f'/proc/{pid_before}/exe').resolve())
requests = root / '.data/whatsapp_ingest/interactive/requests'
before = {p.name for p in requests.glob('*.json')}
result = subprocess.run([node, '--test', *map(str, sorted((root/'services/whatsapp_ingest/test').glob('*.test.mjs')))], cwd=root, capture_output=True, text=True)
(folder/'tests.txt').write_text(result.stdout + result.stderr)
python_result = subprocess.run([sys.executable, '-m', 'pytest', 'tests/test_whatsapp_documents.py', 'tests/test_whatsapp_connected.py', 'tests/test_whatsapp_modes.py', 'tests/test_whatsapp_intake_worker.py', 'tests/test_whatsapp_video.py', 'tests/test_message_flow.py::test_document_message_flow_preserves_opaque_documents', '-q'], cwd=root, capture_output=True, text=True)
(folder/'python-tests.txt').write_text(python_result.stdout + python_result.stderr)
if result.returncode or python_result.returncode:
    print(result.stdout + result.stderr); sys.exit(1)
ctl('restart', unit)
ctl('restart', 'nienfos-whatsapp-intake-worker.service')
connected = False
for _ in range(25):
    try:
        with urlopen('http://127.0.0.1:8787/health', timeout=2) as response:
            health = json.load(response)
        connected = health.get('connection') == 'connected' or health.get('status') == 'connected'
        if connected: break
    except Exception:
        pass
    time.sleep(1)
pid_after = ctl('show', unit, '-p', 'MainPID', '--value')
preserved = before.issubset({p.name for p in requests.glob('*.json')})
active = ctl('is-active', unit) == 'active' and pid_after != pid_before and connected and preserved
receipt = {'tests_passed': result.returncode == 0 and python_result.returncode == 0, 'receiver_connected': connected, 'receiver_active': active, 'requests_preserved': preserved, 'pid_before': pid_before, 'pid_after': pid_after, 'source_sha256': hashlib.sha256((root/'services/whatsapp_ingest/src/message-content.mjs').read_bytes()).hexdigest(), 'human_test': 'pending: resend original certificate and save beside CSR'}
(folder/'activation.json').write_text(json.dumps(receipt, indent=2))
print('NIENFOS_OBSERVATIONS_V1 '+json.dumps({'observations': {'document-intake': result.returncode == 0, 'document-routing': result.returncode == 0 and python_result.returncode == 0, 'active-evidence': active and python_result.returncode == 0}}))
sys.exit(0 if active else 1)
