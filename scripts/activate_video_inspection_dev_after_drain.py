#!/usr/bin/env python3
"""Authorized one-shot activation after existing DEV jobs finish; no forced stop."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/whatsapp-video-inspection-20261005'

def request(path, data=None):
    req=urllib.request.Request('http://127.0.0.1:8118'+path,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=10) as r:return json.load(r)

def record(status, **extra):
    (OUT/'dev-activation.json').write_text(json.dumps({'status':status,'at':time.time(),**extra},indent=2))

def main():
    files=['backend/app/api/routes.py','backend/app/application/services/message_service.py','backend/app/infrastructure/media/video_preview.py','pyproject.toml','uv.lock']
    hashes={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}
    record('waiting_for_active_chats',source_sha256=hashes)
    end=time.monotonic()+7200
    while time.monotonic()<end:
        try:
            drain=request('/maintenance/drain')
            if drain['active_job_count']==0 and drain['in_flight_message_count']==0:
                drain=request('/maintenance/drain',{'requested':True})
                if drain['ready_to_restart']:
                    if any(hashlib.sha256((ROOT/f).read_bytes()).hexdigest()!=h for f,h in hashes.items()):
                        request('/maintenance/drain',{'requested':False});record('pending_source_changed');return 1
                    before=int(subprocess.check_output(['systemctl','--user','show','codex-mobile-bridge-dev.service','-p','MainPID','--value']))
                    record('restarting',pid_before=before,active_jobs=0)
                    try:subprocess.run(['systemctl','--user','restart','codex-mobile-bridge-dev.service'],check=True,timeout=110)
                    except Exception as e:record('restart_uncertain_no_retry',error_type=type(e).__name__);return 1
                    break
                request('/maintenance/drain',{'requested':False})
        except Exception:pass
        time.sleep(5)
    else:record('pending_active_chats');return 1
    for _ in range(45):
        time.sleep(1)
        try:
            h=request('/health')
            if h.get('features',{}).get('video_preview_v1'):
                request('/maintenance/drain',{'requested':False})
                after=int(subprocess.check_output(['systemctl','--user','show','codex-mobile-bridge-dev.service','-p','MainPID','--value']))
                record('activated',pid_before=before,pid_after=after,backend_commit=h['backend_commit'],source_sha256=hashes);break
        except Exception:pass
    else:record('pending_health');return 1
    commands=[
        ('dev-probe-output.txt',[sys.executable,'scripts/probe_video_inspection.py','dev']),
        ('post-dev-check.txt',[sys.executable,'scripts/check_video_inspection.py']),
        ('post-dev-ledger.txt',[sys.executable,'scripts/pipeline_quality.py','--database','.data/pipeline_quality.sqlite3','run','quality-342847b6fc4150beae33a5b6','--attempt','inspection-after-dev-1']),
        ('acceptance.json',[sys.executable,'scripts/pipeline_quality.py','--database','.data/pipeline_quality.sqlite3','evaluate-feedback','requirement-5b3903d984f6253703d80b02'])]
    results={}
    for name,command in commands:
        with (OUT/name).open('w') as log:
            try:results[name]=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=300).returncode
            except subprocess.TimeoutExpired:results[name]=124
    (OUT/'deferred-results.json').write_text(json.dumps(results,indent=2))
    if results['dev-probe-output.txt']==results['post-dev-check.txt']==0:
        report=OUT/'informe.md'
        report.write_text('**Actualización posterior:** DEV activado sin trabajos activos; la prueba de nuevas imágenes y conservación del MP4 pasó también allí. [Comprobaciones](check-evidence.json). La aceptación formal depende del ledger y permanece separada.\n\n'+report.read_text())
    return 0 if results['post-dev-check.txt']==0 else 1

if __name__=='__main__':raise SystemExit(main())
