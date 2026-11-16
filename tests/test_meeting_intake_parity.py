from types import SimpleNamespace
import pytest
from backend.app.application.services.meeting_intake_service import MeetingIntakeService, MeetingIntakeRequest, MeetingIntakeConflict

class Messages:
    def __init__(self, workspace, fail=False):
        self.workspace=workspace; self.sessions={}; self.jobs=[]; self.submits=0; self.fail=fail
    def list_workspaces(self): return [SimpleNamespace(path=str(self.workspace))]
    def get_session(self, sid): return self.sessions.get(sid)
    def create_session(self, **kwargs): self.sessions[kwargs['session_id']]=kwargs
    def list_stored_jobs_for_session(self, sid): return self.jobs
    def update_agent_configuration(self, **kwargs): self.configuration=kwargs['configuration']
    def submit_message(self, *args, **kwargs):
        self.submits+=1
        if self.fail: raise RuntimeError('uncertain provider response')
        self.options=kwargs['codex_options'];job=SimpleNamespace(id='real-test-job');self.jobs.append(job);return job

def request(workspace, **kwargs):
    return MeetingIntakeRequest(delivery_key='a'*64, workspace_path=str(workspace), title='Relevamiento', prompt='Analizar evidencia', **kwargs)

def test_replay_does_not_submit_again(tmp_path, monkeypatch):
    monkeypatch.setenv('CODEX_HOME', str(tmp_path/'codex'))
    messages=Messages(tmp_path);service=MeetingIntakeService(messages,tmp_path/'ledger.sqlite3')
    first=service.launch(request(tmp_path));second=service.launch(request(tmp_path))
    assert first==second and messages.submits==1 and first['state']=='started'
    assert 'sandbox_mode="read-only"' in messages.options.config_overrides
    assert 'features.multi_agent=false' in messages.options.config_overrides

def test_payload_conflict_preserves_original(tmp_path, monkeypatch):
    monkeypatch.setenv('CODEX_HOME',str(tmp_path/'codex'))
    messages=Messages(tmp_path);service=MeetingIntakeService(messages,tmp_path/'ledger.sqlite3')
    original=request(tmp_path);service.launch(original)
    with pytest.raises(MeetingIntakeConflict):service.launch(original.model_copy(update={'prompt':'Otra instrucción'}))
    assert messages.submits==1

def test_uncertain_submission_requires_reconciliation(tmp_path, monkeypatch):
    monkeypatch.setenv('CODEX_HOME',str(tmp_path/'codex'))
    messages=Messages(tmp_path,fail=True);service=MeetingIntakeService(messages,tmp_path/'ledger.sqlite3')
    assert service.launch(request(tmp_path))['state']=='uncertain'
    assert service.launch(request(tmp_path))['state']=='uncertain'
    assert messages.submits==1

def test_attachment_cannot_escape_delivery_cache(tmp_path):
    messages=Messages(tmp_path);service=MeetingIntakeService(messages,tmp_path/'ledger.sqlite3')
    with pytest.raises(ValueError,match='attachment_outside_cache'): service.launch(request(tmp_path,attachments=['../../private.txt']))
    assert messages.submits==0 and not messages.sessions
