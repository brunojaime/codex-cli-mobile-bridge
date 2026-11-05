from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
import pytest
from backend.app.api.feedback_prod_ingress import create_app


def setup(tmp_path, *, environment='prod', upstream_status=202):
    fake=FastAPI(); calls=[]
    @fake.get('/health')
    def health():return {'environment_identity':{'environment':environment}}
    @fake.get('/feedback-workflow-presets')
    def presets():return {'default_preset_id':'default','presets':[]}
    @fake.post('/feedback-batches/start-session', status_code=upstream_status)
    def submit(payload:dict):
        calls.append(payload)
        return {'job_id':'one-prod-job','session_id':'one-prod-session','feedback_batch_id':payload.get('batch_id')}
    app=create_app(backend_url='http://127.0.0.1:8000',ledger_path=tmp_path/'ledger.sqlite3',consumers={'fixture':{'origin':'https://fixture.invalid','workspace':'/fixtures/fixture'}},transport=httpx.ASGITransport(app=fake))
    return TestClient(app),calls


def payload():
    return {'batchId':'stable','sourceApp':'fixture','workspace_path':'fixture','workflowPresetId':'default','items':[{'id':'item','sourceApp':'fixture','comment':'local only','contextMetadata':{'environment':'dev'}}]}


def test_contract_and_same_receipt_without_second_prod_job(tmp_path):
    client,calls=setup(tmp_path)
    assert client.get('/feedback-contract').json()['executorEnvironment']=='prod'
    first=client.post('/feedback-batches/start-session',json=payload())
    assert first.status_code==202
    assert client.post('/bridge-feedback-prod/feedback-batches/start-session',json=payload()).json()==first.json()
    assert len(calls)==1
    assert client.get('/feedback-submissions/stable').json()['state']=='accepted'
    changed={**payload(),'workflowPresetId':'other'}
    assert client.post('/feedback-batches/start-session',json=changed).status_code==409
    assert len(calls)==1


def test_concurrent_replay_admits_one_prod_job(tmp_path):
    client,calls=setup(tmp_path)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results=list(pool.map(lambda _:client.post('/feedback-batches/start-session',json=payload()).status_code,range(12)))
    assert set(results)<= {202,409}
    assert len(calls)==1


@pytest.mark.parametrize('mode',['source','origin','workspace','session','release','environment'])
def test_consumer_scope_is_server_owned(tmp_path,mode):
    client,calls=setup(tmp_path);body=payload();headers={}
    if mode=='source':body['sourceApp']='other'
    if mode=='origin':headers['origin']='https://other.invalid'
    if mode=='workspace':body['workspace_path']='/fixtures/other'
    if mode=='session':body['session_id']='unrelated'
    if mode=='release':body['releaseWhenComplete']=True
    if mode=='environment':body['items'][0]['contextMetadata']['environment']='prod'
    assert client.post('/feedback-batches/start-session',json=body,headers=headers).status_code in (403,422)
    assert calls==[]


def test_no_fallback_to_dev_executor(tmp_path):
    client,calls=setup(tmp_path,environment='dev')
    assert client.post('/feedback-batches/start-session',json=payload()).status_code==503
    assert client.get('/feedback-submissions/stable').status_code==404
    assert calls==[]


def test_uncertain_error_never_blindly_reposts(tmp_path):
    client,calls=setup(tmp_path,upstream_status=500)
    assert client.post('/feedback-batches/start-session',json=payload()).status_code==502
    assert client.get('/feedback-submissions/stable').json()['state']=='uncertain'
    assert client.post('/feedback-batches/start-session',json=payload()).status_code==409
    assert len(calls)==1


def test_trusted_migration_context_preserves_original_admission_identity(tmp_path):
    from backend.app.application.services.feedback_submission import FeedbackSubmissions
    fake=FastAPI();calls=[]
    @fake.get('/health')
    def health():return {'environment_identity':{'environment':'prod'}}
    @fake.post('/feedback-batches/start-session',status_code=202)
    def submit(body:dict):
        calls.append(body);return {'job_id':'one','session_id':'one-session'}
    handoff=tmp_path/'handoff.json';handoff.write_text('{"stable":"Explicit operator continuation context"}')
    app=create_app(backend_url='http://127.0.0.1:8000',ledger_path=tmp_path/'ledger.sqlite3',consumers={'fixture':{'origin':'https://fixture.invalid','workspace':'/fixtures/fixture'}},transport=httpx.ASGITransport(app=fake),handoff_file=handoff)
    client=TestClient(app)
    assert client.post('/feedback-batches/start-session',json=payload()).status_code==202
    assert calls[0]['message']=='Explicit operator continuation context'
    assert client.post('/feedback-batches/start-session',json=payload()).status_code==202
    assert len(calls)==1


def test_unknown_protocol_rejected_before_prod_dispatch(tmp_path):
    client,calls=setup(tmp_path)
    assert client.post('/feedback-batches/start-session',json={**payload(),'version':999}).status_code==422
    assert calls==[]
