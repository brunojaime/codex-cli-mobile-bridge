import copy
import hashlib
import json
from pathlib import Path
import pytest
import httpx
from services.relevamientos.core import Pipeline, atomic, validate_analysis, validate_transcript
from services.relevamientos.drive import Drive, DriveConflict, FOLDER
from services.relevamientos.analyzer import Analyzer

class FakeDrive:
    def __init__(self):
        self.files=[];self.sent={};self.fail=False;self.short=False
    def clients(self):return [{'id':'client','name':'Client'}]
    def recordings(self,c):return copy.deepcopy(self.files)
    def add(self,id='file',version='1'):
        self.files.append({'id':id,'version':version,'name':'meeting.mkv','size':4,'md5Checksum':hashlib.md5(b'data').hexdigest()})
    def download(self,m,p):p.write_bytes(b'x' if self.short else b'data')
    def sync(self,c,j,outputs):
        if self.fail:raise ConnectionError('private token must not be logged')
        for p in outputs.rglob('*'):
            if p.is_file():self.sent[str(p.relative_to(outputs))]=p.read_bytes()

class FakeSpeech:
    def __init__(self):self.calls=0;self.fail=False;self.uncertain=False
    def normalize(self,s,t):t.write_bytes(b'wav')
    def transcribe(self,a):self.calls+=1;return {'raw':'synthetic'}
    def diarize(self,a,aligned):
        if self.fail:raise RuntimeError('private transcription')
        return {'segments':[{'id':'S000001','text':'Requerimos búsqueda','start':0.,'end':2.,'speaker':'SPEAKER_00','uncertain':self.uncertain}]}

class FakeAnalyzer:
    def __init__(self):self.previous=[];self.calls=0
    def analyze(self,job,transcript,speakers,previous):
        self.calls+=1;self.previous=previous
        keys='summary requirements rules stories decisions proposals questions contradictions dependencies risks plan scope_changes supersessions'.split()
        result={k:[] for k in keys}
        result['summary']='Sintético'
        result['requirements']=[{'id':'R'+job,'description':'Búsqueda','kind':'functional','status':'confirmado','references':[{'meeting':job,'segment':'S000001','speaker':'SPEAKER_00','start':0.,'end':2.}]}]
        for old in previous:result['requirements']+=old['analysis']['requirements']
        return result

@pytest.fixture
def env(tmp_path):
    d,s,a=FakeDrive(),FakeSpeech(),FakeAnalyzer();clock=[0.]
    p=Pipeline(tmp_path/'private',d,s,a,clock=lambda:clock[0],settle=60)
    return p,d,s,a,clock

def complete(env):
    p,d,s,a,t=env;d.add();p.tick();t[0]=61;p.tick();return p.jobs()[0]['id']

def test_requested_folder_isolated_idempotent_and_incremental(env):
    p,d,s,a,t=env;d.add()
    d.clients=lambda:[{'id':'client','name':'Patsa'},{'id':'other','name':'Other'}]
    accessed=[]
    def recordings(cid):
        accessed.append(cid)
        return copy.deepcopy(d.files)
    d.recordings=recordings
    def wait(seconds):t[0]+=seconds
    # Pre-existing queued work for another client must remain untouched.
    p.discover([{'id':'other'}]);t[0]+=60;p.discover([{'id':'other'}])
    accessed.clear()
    result=p.requested_folder('patsa','chat:explicit',wait=wait)
    assert result['state']=='completed' and accessed==['client','client']
    assert next(j for j in p.jobs() if j['client']=='other')['state']=='QUEUED'
    p.requested_folder('client','chat:explicit',wait=wait)
    assert s.calls==1 and len(list((p.root/'requests').glob('*.json')))==1
    d.add('new');p.requested_folder('patsa','chat:second',wait=wait)
    assert s.calls==2

def test_requested_folder_rejects_ambiguity_and_missing_reference(env):
    p,d,s,a,t=env
    d.clients=lambda:[{'id':'a','name':'Patsa'},{'id':'b','name':'Patsa'}]
    for folder,ref in [('Patsa','chat:1'),('missing','chat:1'),('a','')]:
        with pytest.raises(ValueError):p.requested_folder(folder,ref,wait=lambda _:None)
    assert not p.jobs() and s.calls==0

def test_discovery_upload_stability_duplicates_and_outputs(env):
    p,d,s,a,t=env
    p.tick();assert not p.jobs() # empty client creates no analysis
    d.add();d.files+=[{'id':'out','version':'1','name':'transcript.md','size':4}]
    p.tick();assert p.jobs()[0]['state']=='WAITING_UPLOAD'
    t[0]=59;p.tick();assert s.calls==0
    d.files[0]['size']=5;t[0]=61;p.tick();assert p.jobs()[0]['state']=='WAITING_UPLOAD'
    d.files[0]['size']=4;t[0]=120;p.tick()
    t[0]=181;p.tick();assert p.jobs()[0]['state']=='COMPLETED'
    p.tick();assert len(p.jobs())==1 and s.calls==1
    assert len(d.sent)==12 and 'estado.json' in d.sent

def test_diarization_failure_resume_restart_without_asr(env):
    p,d,s,a,t=env;s.fail=True;complete(env)
    row=p.jobs()[0];assert row['stage']=='DIARIZING' and row['state']=='FAILED'
    assert 'private' not in row['error']
    p.tick();assert s.calls==1 # backoff
    s.fail=False;t[0]=1000
    restarted=Pipeline(p.root,d,s,a,clock=lambda:t[0]);restarted.tick()
    assert restarted.jobs()[0]['state']=='COMPLETED' and s.calls==1

def test_sync_retry_does_not_repeat_models(env):
    p,d,s,a,t=env;d.fail=True;complete(env)
    assert p.jobs()[0]['stage']=='SYNCING'
    d.fail=False;t[0]=1000;p.tick()
    assert s.calls==1 and a.calls==1 and p.jobs()[0]['state']=='COMPLETED'

def test_checksum_download_failure(env):
    p,d,s,a,t=env;d.short=True;complete(env)
    assert p.jobs()[0]['stage']=='DOWNLOADING' and s.calls==0
    assert p.jobs()[0]['state']=='FAILED'

def test_new_meeting_consolidation(env):
    p,d,s,a,t=env;complete(env);d.add('second');p.tick();t[0]=150;p.tick()
    assert len(p.jobs())==2 and len(a.previous)==1 and s.calls==2
    result=d.sent['consolidado/requerimientos.md'].decode()
    assert all('R'+r['id'] in result for r in p.jobs())

def test_speaker_correction_without_retranscription(env):
    p,d,s,a,t=env;s.uncertain=True;job=complete(env)
    assert p.jobs()[0]['state']=='NEEDS_SPEAKER_REVIEW'
    with pytest.raises(ValueError):p.speakers(job,{'new':'invented'})
    p.speakers(job,{'SPEAKER_00':'Cliente confirmado'});p.tick()
    assert p.jobs()[0]['state']=='COMPLETED' and s.calls==1
    p.speakers(job,{'SPEAKER_00':'Nombre corregido'});p.tick()
    assert s.calls==1 and a.calls==2

def test_lock_and_force_archive(env):
    p,d,s,a,t=env;job=complete(env)
    with p.lock():
        with pytest.raises(BlockingIOError):
            with p.lock():pass
    p.retry(job,reprocess=True);p.tick()
    assert (p.root/(job+'.archive.1')/'transcript.json').exists()
    assert s.calls==2

def test_validation_rejects_hallucinated_trace(env):
    p,d,s,a,t=env;job=complete(env)
    transcript=json.loads((p.root/job/'transcript.json').read_text())
    analysis=json.loads((p.root/job/'analysis.json').read_text())
    analysis['requirements'][0]['references'][0]['start']=900
    with pytest.raises(ValueError):validate_analysis(analysis,{job:transcript})
    transcript['segments'][0]['end']=float('nan')
    with pytest.raises(ValueError):validate_transcript(transcript)

def test_drive_pagination_scope_and_conflict(tmp_path):
    drive=Drive('root',tmp_path/'receipts.json');drive.token='synthetic'
    requests=[]
    def handle(req):
        requests.append(req)
        if req.url.path=='/drive/v3/files':
            q=req.url.params.get('q','')
            if "'root'" in q:
                if not req.url.params.get('pageToken'):return httpx.Response(200,json={'files':[],'nextPageToken':'next'})
                return httpx.Response(200,json={'files':[{'id':'client','name':'c','mimeType':FOLDER}]})
            return httpx.Response(200,json={'files':[{'id':'manual','name':'estado.json','mimeType':'text/plain'}]})
        return httpx.Response(200,content=b'manual correction',headers={'etag':'old'})
    drive.http=httpx.Client(transport=httpx.MockTransport(handle))
    assert drive.clients()[0]['id']=='client'
    with pytest.raises(ValueError):drive.children('unrelated')
    outputs=tmp_path/'outputs';atomic(outputs/'estado.json',{'state':'COMPLETED'})
    with pytest.raises(DriveConflict):drive.sync('client','job',outputs)
    assert all(r.method=='GET' for r in requests)
    assert (tmp_path/'conflict.json').exists()

def test_analysis_tools_disabled_and_bounded(tmp_path,monkeypatch):
    config=tmp_path/'codex';config.mkdir();(config/'config.toml').write_text('[mcp_servers.example]\ncommand="dummy"\n')
    monkeypatch.setenv('CODEX_HOME',str(config))
    analyzer=Analyzer(tmp_path,provider=object())
    opts=analyzer.options().config_overrides
    assert 'features.shell_tool=false' in opts and 'features.apps=false' in opts
    assert 'mcp_servers."example".enabled=false' in opts
    monkeypatch.setenv('RELEVAMIENTOS_MAX_ANALYSIS_BYTES','2')
    with pytest.raises(ValueError):analyzer.analyze('job',{}, {},[])

def test_drive_atomic_upload_repeat_and_conditional_update(tmp_path):
    drive=Drive('root',tmp_path/'receipts.json');drive.token='synthetic'
    remote={};writes=[]
    def handle(req):
        path=req.url.path
        if path=='/drive/v3/files' and req.method=='GET':
            q=req.url.params.get('q','')
            if "'root'" in q:return httpx.Response(200,json={'files':[{'id':'client','name':'c','mimeType':FOLDER}]})
            return httpx.Response(200,json={'files':[{'id':'out','name':'estado.json','mimeType':'text/plain'}] if remote else []})
        if path=='/upload/drive/v3/files' and req.method=='POST':
            boundary=req.headers['content-type'].split('boundary=')[1].encode()
            remote['body']=req.content.split(b'\r\n\r\n')[2].split(b'\r\n--'+boundary)[0]
            writes.append('create');return httpx.Response(200,json={'id':'out'})
        if req.method=='PATCH':
            assert req.headers['if-match']=='"v1"'
            remote['body']=req.content;writes.append('patch');return httpx.Response(200,json={'id':'out'})
        if path=='/drive/v3/files/out':return httpx.Response(200,content=remote['body'],headers={'etag':'"v1"'})
        raise AssertionError(path)
    drive.http=httpx.Client(transport=httpx.MockTransport(handle))
    out=tmp_path/'outputs';atomic(out/'estado.json',{'generation':1})
    drive.sync('client','job',out);drive.sync('client','job',out)
    assert writes==['create']
    atomic(out/'estado.json',{'generation':2});drive.sync('client','job',out)
    assert writes==['create','patch']
    remote['body']=b'user correction';atomic(out/'estado.json',{'generation':3})
    with pytest.raises(DriveConflict):drive.sync('client','job',out)
    assert remote['body']==b'user correction'

def test_drive_download_source_revision_changed(tmp_path):
    drive=Drive('root',tmp_path/'receipt');drive.token='synthetic';drive.allowed.add('client')
    n=[0]
    def handle(req):
        if req.url.params.get('alt')=='media':return httpx.Response(200,content=b'data')
        n[0]+=1
        return httpx.Response(200,json={'version':str(n[0]),'parents':['client']})
    drive.http=httpx.Client(transport=httpx.MockTransport(handle))
    with pytest.raises(ValueError):drive.download({'id':'source','version':'1','size':4},tmp_path/'source')
    assert not (tmp_path/'source').exists()

def test_restart_from_inflight_stage(env):
    p,d,s,a,t=env;job=complete(env)
    p.update(job,'SYNCING',stage='SYNCING')
    p2=Pipeline(p.root,d,s,a,clock=lambda:t[0]);p2.tick()
    assert p2.jobs()[0]['state']=='COMPLETED' and a.calls==s.calls==1

def test_unavailable_download_never_queued(env):
    p,d,s,a,t=env;d.add();d.files[0]['downloadable']=False;p.tick();t[0]=1000;p.tick()
    assert p.jobs()[0]['state']=='WAITING_UPLOAD' and s.calls==0
