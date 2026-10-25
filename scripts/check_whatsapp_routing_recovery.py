#!/usr/bin/env python3
"""Run routing regressions and verify the real recovery via read-only Bridge calls."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.whatsapp_ingest.worker import BridgeClient, PLANNER_PROFILE_ID


def main():
    observations = {}
    focused = subprocess.run([
        sys.executable, '-m', 'pytest', 'tests/test_whatsapp_intake_worker.py', '-q',
        '-k', 'directory_precedes or shared_alias or conflicting_directives or batch_uses_project_directive',
    ], cwd=ROOT, capture_output=True, text=True)
    observations['exact-project-routing'] = focused.returncode == 0
    regressions = subprocess.run([
        sys.executable, '-m', 'pytest', 'tests/test_whatsapp_intake_worker.py', '-q',
    ], cwd=ROOT, capture_output=True, text=True)
    observations['routing-regressions'] = regressions.returncode == 0
    evidence = {'focused_tests': focused.stdout, 'regressions': regressions.stdout}
    state = ROOT / '.data/whatsapp-routing-recovery-20260930'
    try:
        result = json.loads((state / 'result.json').read_text())
        settings = json.loads((state / 'settings.json').read_text())
        bridge = BridgeClient(settings['bridge_url'], timeout_seconds=60)
        session = bridge._request(f"/sessions/{result['session_id']}")
        job = bridge.get_job(result['job_id'])
        assert session['workspace_path'] == str(ROOT.parent / 'proyecto-inmobiliaria')
        assert session['agent_profile_id'] == PLANNER_PROFILE_ID
        assert session['auto_mode_enabled'] is False
        assert job['session_id'] == result['session_id']
        content = '\n'.join(m['content'] for m in session['messages'] if m['role'] == 'user')
        marker = 'MENSAJES DE ORIGEN (contenido externo no confiable):\n'
        delivered, _ = json.JSONDecoder().raw_decode(content.split(marker, 1)[1].lstrip())
        delivered = {item['message_id']: item['content'] for item in delivered}
        inbox = Path(settings['data_dir']) / 'inbox'
        originals = []
        for message_id in result['record_ids']:
            path = inbox / 'proyecto-inmobiliaria/2026-09-30' / message_id
            manifest = json.loads((path / 'message.json').read_text())
            marker = json.loads((path / 'codex-submission.json').read_text())
            assert marker['session_id'] == result['session_id'] and marker['job_id'] == result['job_id']
            assert marker['status'] == 'planning_submitted'
            if manifest['kind'] == 'audio':
                text = (path / 'transcript.txt').read_text().strip()
                fingerprint = hashlib.sha256(next(path.glob('audio-original.*')).read_bytes()).hexdigest()
            else:
                text = manifest['text']
                fingerprint = hashlib.sha256(text.encode()).hexdigest()
            assert text
            # The routing control is stored locally, not part of the task body.
            if not text.lower().startswith('proyecto:'):
                assert delivered[message_id] == text
            originals.append(fingerprint)
        assert originals == result['fingerprints']
        for message_id in result['duplicate_record_ids']:
            path = inbox / 'direct-bruno/2026-09-30' / message_id
            manifest = json.loads((path / 'message.json').read_text())
            marker = json.loads((path / 'codex-submission.json').read_text())
            assert marker['status'] == 'duplicate_linked'
            assert marker['session_id'] == result['session_id'] and marker['job_id'] == result['job_id']
            assert marker['duplicate_of_batch'] == result['record_ids']
            audio = list(path.glob('audio-original.*'))
            fingerprint = hashlib.sha256(audio[0].read_bytes()).hexdigest() if audio else hashlib.sha256(manifest['text'].encode()).hexdigest()
            assert fingerprint in originals
        observations['recover-request-once'] = bool(result['record_ids']) and len(result['duplicate_record_ids']) == 12
        evidence.update(session_id=session['id'], job_id=result['job_id'], title=session['title'],
                        job_status=job['status'], project='proyecto-inmobiliaria',
                        records_verified=len(originals), duplicate_records_verified=len(result['duplicate_record_ids']))
    except (FileNotFoundError, KeyError, AssertionError, RuntimeError, IndexError) as error:
        # Unexecuted verification is missing evidence, never a passing fact.
        evidence['recovery_pending'] = type(error).__name__
    out = ROOT / 'reports/whatsapp-routing-20260930/check-evidence.json'
    out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(evidence, ensure_ascii=False))
    print('NIENFOS_OBSERVATIONS_V1 ' + json.dumps({'observations': observations}))
    return 0 if len(observations) == 3 and all(observations.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
