"""Durable, single-worker meeting pipeline. Adapters never receive client repos."""
from __future__ import annotations
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time

MEDIA = {'.mkv', '.mp4', '.m4a', '.mp3', '.wav', '.webm', '.ogg', '.flac', '.mov'}
OUTPUTS = {'procesadas', 'consolidado'}
STAGES = ('DOWNLOADING', 'TRANSCRIBING', 'DIARIZING', 'ANALYZING', 'SYNCING', 'COMPLETED')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    data = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False, indent=2).encode()
    temp = path.with_suffix(path.suffix + '.tmp')
    with temp.open('wb') as f:
        os.chmod(temp, 0o600)
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    temp.replace(path)


class Pipeline:
    def __init__(self, root, drive, speech, analyzer, *, clock=time.time, settle=60):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)
        self.drive, self.speech, self.analyzer = drive, speech, analyzer
        self.clock, self.settle = clock, settle
        self.db = sqlite3.connect(self.root / 'queue.sqlite3')
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS clients(id TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS jobs(
          id TEXT PRIMARY KEY, client TEXT NOT NULL, metadata TEXT NOT NULL,
          state TEXT NOT NULL, stage TEXT NOT NULL, seen REAL NOT NULL,
          attempts INTEGER NOT NULL DEFAULT 0, retry_at REAL NOT NULL DEFAULT 0,
          error TEXT, generation INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS events(job TEXT, state TEXT, at REAL);
        ''')
        os.chmod(self.root / 'queue.sqlite3', 0o600)

    @contextlib.contextmanager
    def lock(self):
        with (self.root / 'worker.lock').open('a') as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield

    def update(self, job, state, **fields):
        fields['state'] = state
        self.db.execute('UPDATE jobs SET ' + ','.join(k+'=?' for k in fields) + ' WHERE id=?', [*fields.values(), job])
        self.db.execute('INSERT INTO events VALUES(?,?,?)', (job, state, self.clock()))
        self.db.commit()

    def discover(self, clients=None):
        for client in self.drive.clients() if clients is None else clients:
            cid = client['id']
            self.db.execute('INSERT OR IGNORE INTO clients VALUES(?)', (cid,))
            self.db.commit()
            for meta in self.drive.recordings(cid):
                if Path(meta['name']).suffix.lower() not in MEDIA or not meta.get('size') or not meta.get('version'):
                    continue
                key = digest((cid + ':' + meta['id'] + ':' + str(meta['version'])).encode())
                row = self.db.execute('SELECT * FROM jobs WHERE id=?', (key,)).fetchone()
                serialized = json.dumps(meta, sort_keys=True)
                if row is None:
                    self.db.execute('INSERT INTO jobs(id,client,metadata,state,stage,seen) VALUES(?,?,?,?,?,?)', (key,cid,serialized,'DISCOVERED','DOWNLOADING',self.clock()))
                    self.db.commit()
                    self.update(key, 'WAITING_UPLOAD')
                elif row['state'] == 'WAITING_UPLOAD':
                    if row['metadata'] != serialized:
                        self.update(key, 'WAITING_UPLOAD', metadata=serialized, seen=self.clock())
                    elif self.clock()-row['seen'] >= self.settle and meta.get('downloadable', True):
                        self.update(key, 'QUEUED')

    def jobs(self):
        return [dict(r) for r in self.db.execute('SELECT * FROM jobs ORDER BY seen,id')]

    def work(self, client_id=None):
        for row in self.jobs():
            if client_id is not None and row['client'] != client_id:
                continue
            if row['state'] in {'WAITING_UPLOAD','DISCOVERED','COMPLETED','NEEDS_SPEAKER_REVIEW'} or row['retry_at'] > self.clock():
                continue
            self.process(row)

    def tick(self):
        with self.lock():
            self.discover()
            self.work()

    def requested_folder(self, folder, source_ref, wait=time.sleep):
        """One bounded request; never drain work for other clients or poll forever."""
        if not source_ref.strip():
            raise ValueError('request_reference_required')
        with self.lock():
            clients=self.drive.clients()
            matches=[c for c in clients if c['id']==folder or c['name'].casefold()==folder.casefold()]
            if len(matches)!=1:
                raise ValueError('folder_missing_or_ambiguous')
            client=matches[0]
            key=digest((source_ref+':'+client['id']).encode())
            request=self.root/'requests'/(key+'.json')
            if not request.exists():
                atomic(request,{'source_ref':source_ref,'folder_id':client['id'],'state':'requested'})
            self.discover([client])
            # A single stability check is part of this explicit request, not a monitor.
            if any(j['client']==client['id'] and j['state']=='WAITING_UPLOAD' for j in self.jobs()):
                wait(max(0,self.settle))
                self.discover([client])
            self.work(client['id'])
            jobs=[j for j in self.jobs() if j['client']==client['id']]
            atomic(request,{'source_ref':source_ref,'folder_id':client['id'],
                            'state':'completed' if jobs and all(j['state']=='COMPLETED' for j in jobs) else 'pending',
                            'jobs':[{k:j[k] for k in ('id','state','stage','error')} for j in jobs]})
            return json.loads(request.read_text())

    def process(self, row):
        job = row['id']
        directory = self.root / job
        directory.mkdir(exist_ok=True, mode=0o700)
        stage = row['stage']
        meta = json.loads(row['metadata'])
        try:
            for stage in STAGES[STAGES.index(stage):-1]:
                self.update(job, stage, stage=stage)
                if stage == 'DOWNLOADING':
                    target = directory / 'source'
                    self.drive.download(meta, target)
                    if target.stat().st_size != int(meta['size']):
                        raise ValueError('download_size_mismatch')
                    with target.open('rb') as f:
                        sha = hashlib.file_digest(f, 'sha256').hexdigest()
                    if meta.get('md5Checksum'):
                        with target.open('rb') as f:
                            if hashlib.file_digest(f, 'md5').hexdigest() != meta['md5Checksum']:
                                raise ValueError('download_checksum_mismatch')
                    self.speech.normalize(target, directory / 'audio.wav')
                    atomic(directory/'source.json', {'sha256':sha,'drive':meta})
                elif stage == 'TRANSCRIBING':
                    atomic(directory/'aligned.json', self.speech.transcribe(directory/'audio.wav'))
                elif stage == 'DIARIZING':
                    transcript = self.speech.diarize(directory/'audio.wav', json.loads((directory/'aligned.json').read_text()))
                    validate_transcript(transcript)
                    atomic(directory/'transcript.json', transcript)
                    speakers = {s['speaker']:None for s in transcript['segments']}
                    atomic(directory/'speakers.json', speakers)
                elif stage == 'ANALYZING':
                    transcript = json.loads((directory/'transcript.json').read_text())
                    speakers = json.loads((directory/'speakers.json').read_text())
                    if any(s.get('uncertain') for s in transcript['segments']) and not (directory/'review.json').exists():
                        self.update(job, 'NEEDS_SPEAKER_REVIEW', stage='ANALYZING')
                        return
                    previous = []
                    # Include completed meetings, selecting the latest revision of each Drive ID.
                    latest = {}
                    for other in self.jobs():
                        if other['client']==row['client'] and other['id']!=job and other['state']=='COMPLETED':
                            old_meta=json.loads(other['metadata'])
                            old=latest.get(old_meta['id'])
                            if old is None or int(old_meta['version'])>int(json.loads(old['metadata'])['version']):
                                latest[old_meta['id']]=other
                    for other in latest.values():
                        if json.loads(other['metadata'])['id'] != meta['id']:
                            previous.append({'meeting':other['id'],'analysis':json.loads((self.root/other['id']/'analysis.json').read_text()),'transcript':json.loads((self.root/other['id']/'transcript.json').read_text())})
                    analysis=self.analyzer.analyze(job, transcript, speakers, previous)
                    validate_analysis(analysis, {job:transcript, **{p['meeting']:p['transcript'] for p in previous}})
                    atomic(directory/'analysis.json', analysis)
                    render(directory, job, transcript, speakers, analysis)
                elif stage == 'SYNCING':
                    # Receipt persistence and remote optimistic concurrency live in adapter.
                    self.drive.sync(row['client'], job, directory/'outputs')
            self.update(job, 'COMPLETED', stage='COMPLETED', error=None, retry_at=0, attempts=0)
        except Exception as exc:
            # No exception messages: HTTP, model and CLI errors may contain private text/tokens.
            attempts=row['attempts']+1
            self.update(job,'FAILED',stage=stage,error=type(exc).__name__,attempts=attempts,retry_at=self.clock()+min(3600,30*2**min(attempts,7)))

    def retry(self, job, *, reprocess=False):
        row=self.db.execute('SELECT * FROM jobs WHERE id=?',(job,)).fetchone()
        if row is None:
            raise ValueError('unknown_job')
        if reprocess:
            directory=self.root/job
            if directory.exists():
                archive=self.root/(job+'.archive.'+str(row['generation']+1))
                directory.rename(archive)
            self.update(job,'QUEUED',stage='DOWNLOADING',retry_at=0,attempts=0,generation=row['generation']+1)
        else:
            if row['state']!='FAILED':
                raise ValueError('job_not_failed')
            self.update(job,'QUEUED',retry_at=0)

    def speakers(self, job, names):
        directory=self.root/job
        transcript=json.loads((directory/'transcript.json').read_text())
        labels={s['speaker'] for s in transcript['segments']}
        if set(names)!=labels or any(v is not None and (not isinstance(v,str) or len(v)>160) for v in names.values()):
            raise ValueError('invalid_speakers')
        atomic(directory/'speakers.json',names)
        atomic(directory/'review.json',{'confirmed_at':self.clock()})
        self.update(job,'QUEUED',stage='ANALYZING',retry_at=0)


def validate_transcript(data):
    import math
    ids=set()
    for s in data['segments']:
        if s['id'] in ids or not isinstance(s['text'],str) or not s['speaker'].startswith('SPEAKER_'):
            raise ValueError('invalid_segment')
        if not all(math.isfinite(s[k]) for k in ('start','end')) or not 0<=s['start']<s['end']:
            raise ValueError('invalid_times')
        ids.add(s['id'])
    if not ids:
        raise ValueError('no_speech')


def validate_analysis(data, meetings):
    required={'summary','requirements','decisions','proposals','questions','contradictions','dependencies','risks','plan','scope_changes','supersessions','rules','stories'}
    if not required.issubset(data):
        raise ValueError('analysis_sections_missing')
    ids=set()
    for r in data['requirements']:
        if r['id'] in ids or r['status'] not in {'confirmado','propuesto','pendiente'} or r['kind'] not in {'functional','nonfunctional'} or not r['description'] or not r['references']:
            raise ValueError('invalid_requirement')
        ids.add(r['id'])
        for ref in r['references']:
            segment=next((s for s in meetings[ref['meeting']]['segments'] if s['id']==ref['segment']),None)
            if segment is None or any(ref[k]!=segment[k] for k in ('speaker','start','end')):
                raise ValueError('invalid_trace')


def render(directory, job, transcript, speakers, analysis):
    out=directory/'outputs'
    meeting=out/'procesadas'/job
    atomic(meeting/'transcript.json',transcript)
    atomic(meeting/'speakers.json',speakers)
    lines=[f"# Reunión {job}"]
    for s in transcript['segments']:
        lines.append(f"\n[{s['id']}] {s['start']:.2f}–{s['end']:.2f} {s['speaker']} ({speakers.get(s['speaker']) or 'sin nombre confirmado'}): {s['text']}")
    atomic(meeting/'transcript.md','\n'.join(lines).encode())
    groups={'requirements.md':['summary','requirements','rules','stories','dependencies','risks','plan'], 'decisions.md':['decisions','proposals','supersessions'], 'questions.md':['questions','contradictions']}
    for filename,keys in groups.items():
        atomic(meeting/filename,('\n\n'.join('## '+k+'\n\n'+json.dumps(analysis[k],ensure_ascii=False,indent=2) for k in keys)).encode())
    groups={'resumen-cliente.md':['summary','scope_changes'],'requerimientos.md':['requirements','rules','stories'],'decisiones.md':['decisions','proposals','supersessions'],'pendientes.md':['questions','contradictions','dependencies','risks'],'plan-implementacion.md':['plan']}
    for filename,keys in groups.items():
        atomic(out/'consolidado'/filename,('\n\n'.join('## '+k+'\n\n'+json.dumps(analysis[k],ensure_ascii=False,indent=2) for k in keys)).encode())
    atomic(out/'estado.json',{'meeting':job,'state':'COMPLETED','note':'Publicado al terminar los demás artefactos; estado operativo autoritativo en cola SQLite.'})
