#!/usr/bin/env python3
"""One-shot, authorized DEV activation after accepted chats finish; never force stops jobs."""
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'reports/secrets-edit-20261001'
API = 'http://127.0.0.1:8118'
EXPECTED = '5f95b3feaff5'
PACKET = 'quality-71314cb74733cc71b93a44cc'
REQUEST = 'requirement-c877b115dfc62e1205e774dd'


def request(path, body=None):
    req = urllib.request.Request(API + path, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.load(response)


def record(status, **facts):
    data = {'status': status, 'timestamp': time.time(), **facts}
    (REPORT / 'activation.json').write_text(json.dumps(data, indent=2))
    print(json.dumps(data), flush=True)


def main():
    deadline = time.monotonic() + 7200
    record('waiting_for_active_chats', environment='dev')
    while time.monotonic() < deadline:
        try:
            health = request('/health')
            if health.get('backend_commit') == EXPECTED:
                break
            drain = request('/maintenance/drain', {'requested': True})
            if drain['ready_to_restart'] and drain['active_job_count'] == 0:
                record('restarting_dev', active_job_count=0)
                subprocess.run(['systemctl', '--user', 'restart', 'codex-mobile-bridge-dev.service'], check=True, timeout=90)
        except Exception as error:
            record('waiting_or_retrying', error_type=type(error).__name__)
        time.sleep(5)
    else:
        record('pending', reason='Active chats did not drain or expected release did not become healthy')
        try:
            request('/maintenance/drain', {'requested': False})
        except Exception:
            pass
        return 1
    request('/maintenance/drain', {'requested': False})
    record('dev_activated', backend_commit=EXPECTED)
    command = [sys.executable, str(ROOT/'scripts/pipeline_quality.py'), '--database', str(ROOT/'.data/pipeline_quality.sqlite3')]
    with (REPORT/'after-activation.json').open('w') as output:
        run = subprocess.run([*command, 'run', PACKET, '--attempt', 'after-safe-activation-1'], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, timeout=600)
    with (REPORT/'acceptance.json').open('w') as output:
        subprocess.run([*command, 'evaluate-feedback', REQUEST], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, timeout=120)
    acceptance = json.loads((REPORT/'acceptance.json').read_text())
    technical = acceptance.get('technical_verified') is True
    record('verified_technical' if technical else 'pending_evidence', backend_commit=EXPECTED, check_exit_code=run.returncode, semantic_review='not_requested')
    if technical:
        report_path = REPORT/'README.md'
        current = report_path.read_text()
        current = current.replace('| partial |', '| fulfilled |')
        current = current.replace('## Estado de esta entrega', '## Estado inicial de esta entrega (actualización automática al pie)')
        report_path.write_text(current)
    with (REPORT/'README.md').open('a') as output:
        output.write('\nActualización automática: DEV activado. Resultado técnico: **'+('pruebas completas aprobadas' if technical else 'pendiente; revisar evidencia')+'**. [Activación](activation.json), [ejecución registrada](after-activation.json), [aceptación](acceptance.json).\n')
    return 0 if technical else 1


if __name__ == '__main__':
    raise SystemExit(main())
