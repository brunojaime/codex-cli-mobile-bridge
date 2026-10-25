"""Offline integration: real intake/store/worker/API, fake WhatsApp and model."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from test_message_flow import build_session_client, build_session_client_with_container, wait_for_job
from test_whatsapp_intake_worker import FakeBridge, FakeTriage, decision, settings, write_record
from services.whatsapp_ingest.worker import (
    BridgeClient, WhatsAppIntakeWorker, SUBMISSION_FILENAME, encode_multipart_form,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/whatsapp-video.mp4'


@pytest.fixture(autouse=True)
def isolated_acceptance_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv('PIPELINE_QUALITY_DATABASE', str(tmp_path / 'quality.sqlite3'))
    monkeypatch.setenv('PIPELINE_QUALITY_JEV_ENABLED', 'false')


class LocalAPIBridge(BridgeClient):
    def __init__(self, client):
        super().__init__('http://testserver')
        self.client = client
        self.uploads = []

    def _request(self, pathname, *, method='GET', payload=None):
        response = self.client.request(method, pathname, json=payload)
        assert response.is_success, response.text
        return response.json()

    def _request_multipart(self, pathname, *, fields, attachments):
        boundary = 'whatsapp-video-test-boundary'
        response = self.client.post(pathname,
            content=encode_multipart_form(boundary, fields, attachments),
            headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
        assert response.status_code == 202, response.text
        self.uploads.append(response.json())
        return response.json()


@pytest.mark.parametrize('mode', ['project', 'cli'])
@pytest.mark.parametrize('as_document', ['yes', 'no'])
@pytest.mark.parametrize('caption', ['', 'Revisar el recorrido completo'])
def test_video_end_to_end(tmp_path, mode, as_document, caption):
    data, projects = tmp_path / 'data', tmp_path / 'projects'
    project = 'example' if mode == 'project' else 'codex-cli-mobile-bridge'
    workspace = projects / project
    workspace.mkdir(parents=True)
    subprocess.run([shutil.which('node'), str(ROOT / 'tests/fixtures/whatsapp_video_intake.mjs'),
        str(data), str(FIXTURE), mode, as_document, caption], check=True, timeout=20)
    with build_session_client(projects_root=str(projects), codex_workdir=str(ROOT)) as client:
        bridge = LocalAPIBridge(client)
        other = FakeBridge()
        triage = FakeTriage(decision(actionable=False))
        worker = WhatsAppIntakeWorker(settings(data, projects),
            bridge=bridge if mode == 'project' else other,
            direct_cli_bridge=bridge if mode == 'cli' else other, triage=triage)
        assert worker.run_once() == 2
        assert len(bridge.uploads) == 1
        assert not triage.calls
        assert not other.submitted and not other.standard_submitted
        payload = bridge.uploads[0]
        job = wait_for_job(client, payload['job_id'])
        assert job['status'] == 'completed'
        assert 'Document kind: video' in job['response']
        local_path = job['response'].split('Video local path: ', 1)[1].split('\n', 1)[0]
        assert Path(local_path).read_bytes() == FIXTURE.read_bytes()
        session = client.get('/sessions/' + job['session_id']).json()
        assert session['workspace_path'] == str(workspace)
        messages = [m for m in session['messages'] if m['role'] == 'user']
        assert len(messages) == 1
        assert caption in messages[0]['content']
        attachments = messages[0]['attachments']
        assert len(attachments) == 3
        assert [a['kind'] for a in attachments] == ['image', 'image', 'video']
        assert 'sampled frames attached as images' in job['response']
        downloaded = client.get(attachments[-1]['download_url'])
        assert downloaded.status_code == 200
        assert downloaded.content == FIXTURE.read_bytes()
        assert downloaded.headers['content-type'].startswith('video/mp4')
        saved_dir = data / 'inbox' / project / '2026-10-05' / '02-video'
        saved = json.loads((saved_dir / 'message.json').read_text())
        assert saved['video_seconds'] == 1 and saved['mime_type'] == 'video/mp4'
        assert (saved_dir / saved['media_file']).read_bytes() == FIXTURE.read_bytes()
        assert (saved_dir / SUBMISSION_FILENAME).exists()
        assert worker.run_once() == 0
        assert len(bridge.uploads) == 1


def test_video_missing_file_is_not_delivered(tmp_path):
    data, projects = tmp_path / 'data', tmp_path / 'projects'
    (projects / 'example').mkdir(parents=True)
    record = write_record(data, project='example', message_id='video', kind='text')
    manifest = json.loads((record / 'message.json').read_text())
    manifest.update(kind='video', media_file='video-original.mp4')
    (record / 'message.json').write_text(json.dumps(manifest))
    bridge = FakeBridge()
    worker = WhatsAppIntakeWorker(settings(data, projects), bridge=bridge,
        triage=FakeTriage(decision(actionable=True)))
    assert worker.run_once() == 0
    assert not bridge.submitted
    assert not (record / SUBMISSION_FILENAME).exists()
    # Recovery preserves the record and can deliver the original on the next pass.
    (record / 'video-original.mp4').write_bytes(FIXTURE.read_bytes())
    assert worker.run_once() == 1
    assert bridge.submitted[0]['attachment_paths'] == [record / 'video-original.mp4']
    assert worker.run_once() == 0


def test_video_group_context_and_delivery(tmp_path):
    data, projects = tmp_path / 'data', tmp_path / 'projects'
    (projects / 'example').mkdir(parents=True)
    records = []
    for name, caption in [('older', None), ('newer', 'Revisar video')]:
        record = write_record(data, project='example', message_id=name, kind='text')
        manifest = json.loads((record / 'message.json').read_text())
        manifest.update(kind='video', media_file='video-original.mp4', text=caption)
        (record / 'message.json').write_text(json.dumps(manifest))
        (record / 'video-original.mp4').write_bytes(FIXTURE.read_bytes())
        records.append(record)
    bridge = FakeBridge()
    triage = FakeTriage(decision(actionable=True))
    worker = WhatsAppIntakeWorker(settings(data, projects), bridge=bridge, triage=triage)
    prepared = worker._prepare_record(records[1])
    context = worker._recent_context([prepared])
    assert context[0]['content'] == '[Video adjunto]'
    assert worker.run_once() == 2
    assert len(triage.calls) == 1
    assert set(bridge.submitted[0]['attachment_paths']) == {r / 'video-original.mp4' for r in records}


def test_video_paths_persist_and_migrate_sqlite(tmp_path):
    import sqlite3
    from backend.app.domain.entities.chat_session import ChatSession
    from backend.app.domain.entities.job import Job
    from backend.app.infrastructure.persistence.sqlite_chat_repository import SqliteChatRepository

    database = tmp_path / 'chat.sqlite3'
    repository = SqliteChatRepository(database_path=str(database), projects_root=str(tmp_path))
    repository.save_session(ChatSession(id='session', title='test', workspace_path=str(tmp_path), workspace_name='test'))
    repository.save_job(Job(id='old', session_id='session', message='old'))
    # Recreate the previous schema, then exercise the additive migration.
    with sqlite3.connect(database) as connection:
        connection.execute('ALTER TABLE jobs DROP COLUMN video_paths_json')
    repository = SqliteChatRepository(database_path=str(database), projects_root=str(tmp_path))
    assert repository.get_job('old').video_paths == []
    job = Job(id='video', session_id='session', message='video', video_paths=[str(FIXTURE)])
    repository.save_job(job)
    reopened = SqliteChatRepository(database_path=str(database), projects_root=str(tmp_path))
    assert reopened.get_job('video').video_paths == [str(FIXTURE)]
    job.video_paths.append(str(FIXTURE))
    reopened.save_job(job)
    assert reopened.get_job('video').video_paths == [str(FIXTURE), str(FIXTURE)]


def test_video_download_bounds_retry_and_mixed_images(tmp_path):
    client, container = build_session_client_with_container()
    response = client.post('/message/attachments', data={'message': 'Check files'}, files=[
        ('attachments', ('test.mp4', FIXTURE.read_bytes(), 'video/mp4')),
        ('attachments', ('test.png', b'fake image', 'image/png')),
    ])
    assert response.status_code == 202
    job_id = response.json()['job_id']
    job = wait_for_job(client, job_id)
    assert job['status'] == 'completed'
    assert client.get(f'/jobs/{job_id}/attachments/2').content == b'fake image'
    assert client.get(f'/jobs/{job_id}/attachments/3').content == FIXTURE.read_bytes()
    assert client.get(f'/jobs/{job_id}/attachments/-1').status_code == 404
    assert client.get(f'/jobs/{job_id}/attachments/4').status_code == 404
    retried = client.post(f'/jobs/{job_id}/retry')
    assert retried.is_success, retried.text
    assert client.get(f"/jobs/{retried.json()['job_id']}/attachments/3").content == FIXTURE.read_bytes()
    repository = container.message_service._repository
    stored = repository.get_job(job_id)
    stored.video_paths = [str(FIXTURE)]  # Exists, but outside managed attachment storage.
    repository.save_job(stored)
    assert client.get(f'/jobs/{job_id}/attachments/3').status_code == 404
    stored.video_paths = [str(tmp_path / 'missing.mp4')]
    repository.save_job(stored)
    assert client.get(f'/jobs/{job_id}/attachments/3').status_code == 404
