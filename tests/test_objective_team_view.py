import hashlib
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.objective_team_routes import router, get_view, get_container
from backend.app.application.services.objective_team_view import ObjectiveTeamView


@pytest.fixture
def rig(tmp_path):
    workspace = tmp_path / 'project'
    workspace.mkdir()
    root = tmp_path / 'state'
    run_id = 'a' * 24
    run = root / 'runs' / run_id
    run.mkdir(parents=True)
    state = {'id': run_id, 'request': {'workspace': str(workspace), 'objective': 'Una app útil',
             'max_calls': 32, 'sources': ['PRIVATE'], 'verification_commands': ['SECRET']},
             'status': 'final_review', 'head': 'b' * 40, 'delivery': {'implemented': True},
             'units': [{'id': 'u1', 'state': 'accepted', 'stories': ['S1']}],
             'spec': {'stories': [{'id': 'S1', 'acceptance': ['Funciona']}]},
             'jobs': [], 'issues': {}, 'events': []}
    file = run / 'state.json'
    file.write_text(json.dumps(state))
    view = ObjectiveTeamView(root, [SimpleNamespace(path=str(workspace), name='Proyecto')])
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_view] = lambda: view
    app.dependency_overrides[get_container] = lambda: SimpleNamespace(settings=SimpleNamespace(bridge_environment='dev'))
    return SimpleNamespace(view=view, state=state, file=file, run=run, root=root,
                           id=run_id, client=TestClient(app))


def test_projection_does_not_confuse_implementation_with_verification(rig):
    before = rig.file.read_bytes()
    response = rig.client.get('/objective-team/' + rig.id)
    assert response.status_code == 200
    result = response.json()
    assert result['delivery'] == {'implemented': True, 'verified': False, 'applied': False}
    assert result['can_open_chats'] is False
    assert result['stories'][0]['state'] == 'accepted'
    assert 'PRIVATE' not in response.text and 'SECRET' not in response.text
    assert rig.file.read_bytes() == before
    assert rig.client.post('/objective-team/' + rig.id).status_code == 405


def test_unregistered_workspace_and_invalid_id_cannot_be_read(rig):
    rig.state['request']['workspace'] = '/unregistered'
    rig.file.write_text(json.dumps(rig.state))
    assert rig.client.get('/objective-team').json()['runs'] == []
    assert rig.client.get('/objective-team/' + rig.id).status_code == 404
    assert rig.client.get('/objective-team/not-an-id').status_code == 404
    assert rig.client.get('/objective-team?workspace_path=/unregistered').status_code == 404


def test_corrupt_state_is_not_reported_as_successful_empty_list(rig):
    rig.file.write_text('{invalid')
    assert rig.client.get('/objective-team').json()['unavailable'] == 1
    assert rig.client.get('/objective-team/' + rig.id).status_code == 503


def test_image_is_bounded_to_evidence_and_hash_checked(rig):
    evidence = rig.run / 'evidence' / ('b' * 40)
    evidence.mkdir(parents=True)
    image = evidence / 'desktop.png'
    data = b'\x89PNG\r\n\x1a\nEXAMPLE'
    image.write_bytes(data)
    outside = rig.root / 'secret.png'
    outside.write_bytes(data)
    link = evidence / 'escape.png'
    link.symlink_to(outside)
    rig.state['jobs'] = [{'result': {'verified_image_files': [
        {'path': str(p), 'sha256': hashlib.sha256(data).hexdigest(), 'commit': 'b' * 40}
        for p in (image, outside, link)]}}]
    rig.file.write_text(json.dumps(rig.state))
    images = rig.client.get('/objective-team/' + rig.id).json()['images']
    assert len(images) == 1
    url = f'/objective-team/{rig.id}/images/{images[0]["id"]}'
    response = rig.client.get(url)
    assert response.content == data and response.headers['content-type'] == 'image/png'
    assert 'no-store' in response.headers['cache-control']
    image.write_bytes(data + b'MODIFIED')
    assert rig.client.get(url).status_code == 503
    assert rig.client.get(f'/objective-team/{rig.id}/images/unknown').status_code == 404


def test_ux_proposal_is_visible_but_not_claimed_reviewed(rig):
    workspace = rig.root / 'ux-job'
    workspace.mkdir()
    image = workspace / 'proposal-a.png'
    image.write_bytes(b'\x89PNG\r\n\x1a\nPROPOSAL')
    rig.state['jobs'] = [{'role': 'ux', 'key': 'ux-job', 'workspace': str(workspace),
        'result': {'commit': 'c' * 40, 'evidence': [
            {'kind': 'screenshot', 'reference': 'proposal-a.png'},
            {'kind': 'screenshot', 'reference': str(rig.file)}]}}]
    rig.file.write_text(json.dumps(rig.state))
    images = rig.client.get('/objective-team/' + rig.id).json()['images']
    assert len(images) == 1 and images[0]['reviewed'] is False
    assert images[0]['commit'] == 'c' * 40


def test_monitor_caches_discovery_but_always_reads_current_progress(rig, monkeypatch):
    import io
    from backend.app import objective_team_server as server
    calls = []
    class Opener:
        def open(self, url, timeout):
            calls.append(url)
            return io.BytesIO(json.dumps([{'path': rig.state['request']['workspace'],
                                          'name': 'Proyecto'}]).encode())
    monkeypatch.setattr(server, 'build_opener', lambda *args: Opener())
    client = TestClient(server.create_monitor(rig.root, 8000, 'prod'))
    assert client.get('/objective-team/' + rig.id).json()['status'] == 'final_review'
    rig.state['status'] = 'completed'
    rig.file.write_text(json.dumps(rig.state))
    assert client.get('/objective-team/' + rig.id).json()['status'] == 'completed'
    assert len(calls) == 1
    monkeypatch.setattr(server, 'monotonic', lambda: float('inf'))
    assert client.get('/objective-team').status_code == 200
    assert len(calls) == 2
