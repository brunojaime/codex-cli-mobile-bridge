#!/usr/bin/env python3
"""Authorized one-shot DEV activation; wait for every accepted job to finish."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reports/whatsapp-videos-20261005'
API = 'http://127.0.0.1:8118'


def request(path, body=None):
    req = urllib.request.Request(API + path, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.load(response)


def record(status, **facts):
    result = {'status': status, 'checked_at': time.time(), 'authorization': 'source-b2848ef6d151d74560192d1f', **facts}
    (OUT / 'dev-activation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)


def main():
    files = ['backend/app/api/schemas.py', 'backend/app/application/services/message_service.py', 'backend/app/domain/entities/job.py', 'backend/app/infrastructure/persistence/sqlite_chat_repository.py']
    hashes = {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in files}
    deadline = time.monotonic() + 7200
    record('waiting_for_active_chats', source_sha256=hashes)
    while time.monotonic() < deadline:
        try:
            d = request('/maintenance/drain')
            if d['active_job_count'] == 0 and d['in_flight_message_count'] == 0:
                d = request('/maintenance/drain', {'requested': True})
                if d['ready_to_restart'] and d['active_job_count'] == 0:
                    if any(hashlib.sha256((ROOT/f).read_bytes()).hexdigest() != hashes[f] for f in files):
                        request('/maintenance/drain', {'requested': False})
                        record('pending_source_changed'); return 1
                    before = int(subprocess.check_output(['systemctl', '--user', 'show', 'codex-mobile-bridge-dev.service', '-p', 'MainPID', '--value']))
                    record('restarting', active_job_count=0, pid_before=before)
                    try:
                        subprocess.run(['systemctl', '--user', 'restart', 'codex-mobile-bridge-dev.service'], check=True, timeout=110)
                    except Exception as error:
                        record('restart_uncertain_no_automatic_retry', error_type=type(error).__name__)
                        return 1
                    break
                request('/maintenance/drain', {'requested': False})
        except Exception as error:
            record('waiting', error_type=type(error).__name__)
        time.sleep(5)
    else:
        record('pending_active_chats'); return 1
    for _ in range(60):
        try:
            h = request('/health')
            schema = request('/openapi.json')['components']['schemas']['ChatMessageAttachmentResponse']['properties']['kind']
            if 'video' in schema.get('enum', []):
                request('/maintenance/drain', {'requested': False})
                after = int(subprocess.check_output(['systemctl', '--user', 'show', 'codex-mobile-bridge-dev.service', '-p', 'MainPID', '--value']))
                record('activated', pid_before=before, pid_after=after, health=h['status'], source_sha256=hashes, video_schema=schema)
                break
        except Exception:
            pass
        time.sleep(1)
    else:
        record('pending_health_check'); return 1
    with (OUT/'post-dev-check.txt').open('w') as log:
        result = subprocess.run([sys.executable, str(ROOT/'scripts/check_whatsapp_video_activation.py')], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=240)
    command = [sys.executable, str(ROOT/'scripts/pipeline_quality.py'), '--database', str(ROOT/'.data/pipeline_quality.sqlite3')]
    with (OUT/'post-dev-ledger-run.json').open('w') as log, (OUT/'post-dev-ledger-error.txt').open('w') as error:
        subprocess.run([*command, 'run', 'quality-f582f85fa93e396cd756ac26', '--attempt', 'after-dev-activation-1'], cwd=ROOT, stdout=log, stderr=error, timeout=300)
    with (OUT/'activation-acceptance.json').open('w') as log:
        subprocess.run([*command, 'evaluate-feedback', 'requirement-f8a82450994ef8db0c3eb2c4'], cwd=ROOT, stdout=log, stderr=subprocess.DEVNULL, timeout=60)
    with (OUT/'dev-activation-update.md').open('w') as report:
        report.write('DEV activado después de finalizar los chats en curso. Comprobación posterior: '+('aprobada' if result.returncode == 0 else 'parcial; consultar hechos pendientes')+'.\n\n[Estado y procesos](dev-activation.json) · [Pruebas de los servicios](activation-check.json) · [Transporte DEV](dev-probe.json)\n')
    if result.returncode == 0:
        report = OUT/'activacion.md'
        report.write_text('**Actualización automática posterior:** DEV ya fue activado y la comprobación de transporte pasó en ambos backends. [Resultado ejecutado](dev-activation-update.md). La recepción desde WhatsApp real y el recibo formal del ledger siguen pendientes.\n\n' + report.read_text())
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
