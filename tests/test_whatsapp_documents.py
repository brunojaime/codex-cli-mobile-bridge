"""Opaque document through intake, routing, multipart and local Bridge API. No credentials."""
import json
from pathlib import Path
import shutil
import subprocess
import pytest
from test_message_flow import build_session_client, wait_for_job
from test_whatsapp_video import LocalAPIBridge
from test_whatsapp_intake_worker import FakeBridge, FakeTriage, decision, settings
from services.whatsapp_ingest.worker import WhatsAppIntakeWorker

ROOT = Path(__file__).resolve().parents[1]

@pytest.mark.parametrize('mode', ['project', 'cli'])
@pytest.mark.parametrize('filename', ['certificado.crt', 'solicitud.csr', 'archivo.bin', '../../certificate.crt'])
def test_opaque_document_intake_to_api(tmp_path, monkeypatch, mode, filename):
    monkeypatch.setenv('PIPELINE_QUALITY_DATABASE', str(tmp_path / 'quality.sqlite3'))
    monkeypatch.setenv('PIPELINE_QUALITY_JEV_ENABLED', 'false')
    data, projects = tmp_path / 'data', tmp_path / 'projects'
    project = 'example' if mode == 'project' else 'codex-cli-mobile-bridge'
    workspace = projects / project
    workspace.mkdir(parents=True)
    content = b'\x00\xff\x80\r\nsynthetic-certificate\x00'
    source = tmp_path / 'fixture.bin'
    source.write_bytes(content)
    subprocess.run([shutil.which('node'), str(ROOT / 'tests/fixtures/whatsapp_document_intake.mjs'),
                    str(data), str(source), mode, filename, 'Guardar archivo'], check=True, timeout=20)
    with build_session_client(projects_root=str(projects), codex_workdir=str(ROOT)) as client:
        bridge, other = LocalAPIBridge(client), FakeBridge()
        triage = FakeTriage(decision(actionable=False))
        worker = WhatsAppIntakeWorker(settings(data, projects), bridge=bridge if mode == 'project' else other,
                    direct_cli_bridge=bridge if mode == 'cli' else other, triage=triage)
        assert worker.run_once() == 2
        assert len(bridge.uploads) == 1
        assert not triage.calls
        job = wait_for_job(client, bridge.uploads[0]['job_id'])
        assert job['status'] == 'completed'
        assert 'Document kind: file' in job['response']
        retained = job['response'].split('Original file local path: ', 1)[1].splitlines()[0]
        assert Path(retained).read_bytes() == content
        assert 'Content type: application/pkix-cert' in job['response']
        session = client.get('/sessions/' + job['session_id']).json()
        assert session['workspace_path'] == str(workspace)
        user = next(m for m in session['messages'] if m['role'] == 'user')
        safe = Path(filename).name
        assert safe in user['content']
        assert '../' not in user['content']
        saved_dir = data / 'inbox' / project / '2026-10-05' / '02-document'
        saved = json.loads((saved_dir / 'message.json').read_text())
        assert saved['original_filename'] == filename
        assert (saved_dir / saved['media_file']).read_bytes() == content
        assert worker.run_once() == 0
        assert len(bridge.uploads) == 1
