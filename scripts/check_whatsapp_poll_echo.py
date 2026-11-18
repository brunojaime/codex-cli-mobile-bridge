#!/usr/bin/env python3
"""Executed local probe evidence; never exports poll encryption material."""
import json
import subprocess
import os
from pathlib import Path
from urllib.request import urlopen

root = Path(__file__).resolve().parents[1]
service_env = {**os.environ, 'XDG_RUNTIME_DIR': f'/run/user/{os.getuid()}', 'DBUS_SESSION_BUS_ADDRESS': f'unix:path=/run/user/{os.getuid()}/bus'}
pid = subprocess.check_output(['systemctl', '--user', 'show', 'nienfos-whatsapp-ingest.service', '-p', 'MainPID', '--value'], text=True, env=service_env).strip()
node = str(Path(f'/proc/{pid}/exe').resolve())
tests = sorted((root / 'services/whatsapp_ingest/test').glob('*.test.mjs'))
result = subprocess.run([node, '--test', *map(str, tests)], cwd=root, capture_output=True, text=True)
folder = root / 'reports/whatsapp-poll-echo-20261026'
folder.mkdir(parents=True, exist_ok=True)
(folder / 'tests.tap').write_text(result.stdout + result.stderr)
state = json.loads((root / '.data/whatsapp_ingest/poll-echo.json').read_text())
with urlopen('http://127.0.0.1:8787/health', timeout=5) as response:
    health = json.load(response)
submitted = [v for v in state.get('votes', {}).values() if v['status'] == 'submitted']
evidence = {
    'poll_id': state.get('poll_id'), 'status': state['status'],
    'sent_at': state.get('sent_at'), 'receiver_connected': health.get('connection') == 'connected',
    'tests_passed': result.returncode == 0,
    'replies': [{k: v.get(k) for k in ('option', 'reply_id', 'at')} for v in submitted],
    'human_receipt': 'pending',
}
(folder / 'receipt.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
observations = {}
if result.returncode == 0:
    observations['scoped-tests'] = True
if health.get('connection') == 'connected' and state.get('poll_id') and result.returncode == 0:
    observations['local-activation'] = True
if submitted:
    observations['real-vote-reply'] = all(v.get('reply_id') and v['option'] in state['options'] for v in submitted)
print('NIENFOS_OBSERVATIONS_V1 ' + json.dumps({'observations': observations}))
raise SystemExit(result.returncode)
