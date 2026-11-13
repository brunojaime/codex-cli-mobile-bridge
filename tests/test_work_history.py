from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from test_work_coordinator import rig, work, request
from backend.app.api.work_routes import router, get_container


def test_history_pages_terminal_work_and_scopes_before_pagination(work, monkeypatch, tmp_path):
    first = str(work.rig.workspace)
    other = str(tmp_path / 'another-project')
    monkeypatch.setattr(work.rig.messages, 'list_workspaces', lambda: [
        SimpleNamespace(path=first, name='First'), SimpleNamespace(path=other, name='Other')])
    ids = []
    for i in range(9):
        t = work.service.enqueue(request(work, f'item-{i}'))
        ids.append(t['id'])
        with work.service.ledger() as db:
            db.execute('UPDATE work_tasks SET status=?,workspace=? WHERE id=?',
                       ('completed' if i < 6 else 'cancelled' if i == 6 else 'queued',
                        other if i < 2 else first, t['id']))
            db.commit()
    page = work.service.history(first, limit=2)
    assert len(page['tasks']) == 2
    assert all(t['workspace_path'] == first for t in page['tasks'])
    assert page['tasks'][0]['status'] == 'cancelled'
    seen = [t['id'] for t in page['tasks']]
    while page['next_cursor']:
        page = work.service.history(first, cursor=page['next_cursor'], limit=2)
        seen.extend(t['id'] for t in page['tasks'])
    assert len(seen) == len(set(seen)) == 5
    assert set(seen) == set(ids[2:7])
    assert len(work.service.history()['tasks']) == 7
    with pytest.raises(ValueError): work.service.history('/unknown')
    with pytest.raises(ValueError): work.service.history(cursor='invalid')
    assert not work.rig.provider.requests


def test_history_http_validation_and_archive_survives_removal(work):
    task = work.service.enqueue(request(work))
    work.service.control(task['id'], task['revision'], 'cancel')
    app = FastAPI()
    app.dependency_overrides[get_container] = lambda: SimpleNamespace(work_coordinator_service=work.service)
    app.include_router(router)
    with TestClient(app) as client:
        response = client.get('/work/history', params={'workspace_path': str(work.rig.workspace)})
        assert response.status_code == 200
        assert response.json()['tasks'][0]['status'] == 'cancelled'
        assert not work.service.overview()['projects'][0]['queue']
        assert client.get('/work/history', params={'limit': 0}).status_code == 422
        assert client.get('/work/history', params={'cursor': 'bad'}).status_code == 422
    assert not work.rig.provider.requests
