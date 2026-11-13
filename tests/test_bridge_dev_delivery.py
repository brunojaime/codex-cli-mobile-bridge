import hashlib
import json
from pathlib import Path

import httpx
import pytest

from scripts.project_work import bridge_dev_delivery as delivery


def setup_plan(tmp_path):
    runtime, stage = tmp_path / 'runtime', tmp_path / 'stage'
    runtime.mkdir(); stage.mkdir()
    (runtime / 'file.py').write_text('before')
    (stage / 'file.py').write_text('after')
    config = {'runtime': str(runtime), 'checkout': str(tmp_path), 'report': str(tmp_path / 'state.json'), 'branch': 'dev/fix'}
    plan = {'runtime': str(runtime), 'stage': str(stage), 'revision': 'a' * 40, 'files': {'file.py': {'before': hashlib.sha256(b'before').hexdigest(), 'after': hashlib.sha256(b'after').hexdigest()}}}
    config_path, plan_path = tmp_path / 'config.json', tmp_path / 'plan.json'
    config_path.write_text(json.dumps(config)); plan_path.write_text(json.dumps(plan))
    return config_path, plan_path, runtime


def mock_client(monkeypatch, environment='dev', busy=False):
    original = httpx.Client
    def respond(request):
        if request.url.path == '/health':
            return httpx.Response(200, json={'environment_identity': {'environment': environment}})
        assert request.url.path == '/maintenance/drain'
        return httpx.Response(200, json={'requested': False, 'active_job_count': int(busy), 'active_session_count': int(busy), 'in_flight_message_count': int(busy)})
    monkeypatch.setattr(delivery.httpx, 'Client', lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(respond)))


def test_active_conversation_prevents_any_write_or_restart(tmp_path, monkeypatch):
    config, plan, runtime = setup_plan(tmp_path)
    mock_client(monkeypatch, busy=True)
    monkeypatch.setattr(delivery, 'run', lambda *a, **k: pytest.fail('No command should run while busy'))
    monkeypatch.setattr(delivery.time, 'sleep', lambda _: (_ for _ in ()).throw(TimeoutError('still busy')))
    with pytest.raises(TimeoutError):
        delivery.activate(config, plan)
    assert (runtime / 'file.py').read_text() == 'before'
    assert json.loads((tmp_path / 'state.json').read_text())['state'] == 'waiting_for_idle'


def test_concurrent_runtime_change_is_preserved(tmp_path, monkeypatch):
    config, plan, runtime = setup_plan(tmp_path)
    (runtime / 'file.py').write_text('someone else changed this')
    mock_client(monkeypatch)
    monkeypatch.setattr(delivery, 'run', lambda args, *a, **k: str(runtime / 'main.py') if args[:3] == ['systemctl', '--user', 'show'] else pytest.fail('No restart allowed'))
    with pytest.raises(AssertionError, match='source changed'):
        delivery.activate(config, plan)
    assert (runtime / 'file.py').read_text() == 'someone else changed this'


def test_production_identity_is_rejected(tmp_path, monkeypatch):
    config, plan, runtime = setup_plan(tmp_path)
    mock_client(monkeypatch, environment='prod')
    monkeypatch.setattr(delivery, 'run', lambda *a, **k: pytest.fail('No command allowed on production'))
    with pytest.raises(AssertionError):
        delivery.activate(config, plan)
    assert (runtime / 'file.py').read_text() == 'before'
