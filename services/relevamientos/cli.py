"""Operator commands. Status intentionally omits recording names and transcripts."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import shlex
from backend.app.infrastructure.config.settings import Settings
from backend.app.container import _agent_cli
import time
from .core import Pipeline
from .drive import Drive
from .speech import Speech
from .analyzer import Analyzer

ROOT_ID='1bSaRi8H3UoAguICer0_wedqkZukArzi5'

def doctor():
    needed=['RELEVAMIENTOS_GOOGLE_CLIENT_ID','RELEVAMIENTOS_GOOGLE_CLIENT_SECRET','RELEVAMIENTOS_GOOGLE_REFRESH_TOKEN','HF_TOKEN']
    argv=json.loads(os.environ.get('RELEVAMIENTOS_SPEECH_ARGV','[".venv-relevamientos/bin/python"]'))
    return {'ffmpeg':bool(shutil.which(os.environ.get('RELEVAMIENTOS_FFMPEG','ffmpeg'))),'speech_executable':bool(shutil.which(argv[0])),'missing_secret_names':[k for k in needed if not os.environ.get(k)],'codex':bool(shutil.which(shlex.split(_agent_cli(Settings()).command)[0])),'root_id':os.environ.get('RELEVAMIENTOS_DRIVE_ROOT_ID',ROOT_ID)}

def main():
    os.umask(0o077)
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',default='.data/relevamientos')
    sub=p.add_subparsers(dest='command',required=True)
    for name in ('doctor','status'):sub.add_parser(name)
    request=sub.add_parser('run')
    request.add_argument('--folder',required=True)
    request.add_argument('--source-ref',required=True)
    for name in ('retry','reprocess','speakers'):
        c=sub.add_parser(name);c.add_argument('job')
        if name=='speakers':c.add_argument('--file',required=True)
    a=p.parse_args()
    if a.command=='doctor':print(json.dumps(doctor(),indent=2));return
    pipeline=Pipeline(a.root,Drive(os.environ.get('RELEVAMIENTOS_DRIVE_ROOT_ID',ROOT_ID),Path(a.root)/'drive-receipts.json'),Speech(),Analyzer(a.root),settle=int(os.environ.get('RELEVAMIENTOS_SETTLE_SECONDS','60')))
    if a.command=='status':
        print(json.dumps([{k:r[k] for k in ('id','state','stage','attempts','retry_at','error')} for r in pipeline.jobs()],indent=2));return
    if a.command in {'retry','reprocess','speakers'}:
        with pipeline.lock():
            if a.command=='speakers':pipeline.speakers(a.job,json.loads(Path(a.file).read_text()))
            else:pipeline.retry(a.job,reprocess=a.command=='reprocess')
        return
    readiness=doctor()
    if readiness['missing_secret_names'] or not readiness['ffmpeg'] or not readiness['speech_executable'] or not readiness['codex']:
        print(json.dumps({'state':'BLOCKED','readiness':readiness}));raise SystemExit(2)
    try:
        result=pipeline.requested_folder(a.folder,a.source_ref)
        print(json.dumps(result),flush=True)
        if result['state']!='completed':raise SystemExit(2)
    except Exception as exc:
        print(json.dumps({'event':'request_failed','error':type(exc).__name__}),flush=True)
        raise SystemExit(2)

if __name__=='__main__':main()
