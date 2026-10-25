#!/usr/bin/env python3
"""Executed evidence; real API inspection and bounded local regression checks."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reports/whatsapp-video-inspection-20261005'

def request(port, path):
    with urllib.request.urlopen(f'http://127.0.0.1:{port}'+path, timeout=10) as r:
        return json.load(r)

def identity(port):
    h=request(port,'/health')
    return {'environment':h['environment_identity']['environment'],
            'origin':'https://batata-default-string.tail0302c4.ts.net'+(':8443' if port==8118 else ''),
            'release_id':h['backend_commit']+(':video-preview-v1' if h.get('features',{}).get('video_preview_v1') else ':no-video-preview')}

def main():
    before=identity(8118)
    with (OUT/'registered-tests.txt').open('w') as log:
        test=subprocess.run([sys.executable,'-m','pytest','tests/test_video_preview.py','tests/test_whatsapp_video.py','-q'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=180)
    facts={'bounded-honest':test.returncode==0}
    recovery=json.loads((OUT/'recovery.json').read_text())
    session=request(8000,'/sessions/'+recovery['session_id'])
    messages=[m for m in session['messages'] if m['role']=='user' and m['content'].startswith('Corrección técnica del adjunto')]
    hashes=[]
    if len(messages)==1:
        for attachment in messages[0]['attachments']:
            with urllib.request.urlopen('http://127.0.0.1:8000'+attachment['download_url'],timeout=10) as r:
                hashes.append(hashlib.sha256(r.read()).hexdigest())
    facts['real-videos']=len(hashes)==17 and hashes==recovery['frame_sha256'] and session['workspace_path']=='/home/batata/Projects/peluquerias'
    probes=[]
    for env,port in [('prod',8000),('dev',8118)]:
        path=OUT/f'{env}-probe.json'
        if path.exists():
            state=json.loads(path.read_text())
            session=request(port,'/sessions/'+state['session_id'])
            user=next((m for m in session['messages'] if m['role']=='user' and m['content'].startswith('PRUEBA INSPECCIÓN VIDEO V1')),None)
            if user:
                kinds=[a['kind'] for a in user['attachments']]
                original=user['attachments'][-1]
                with urllib.request.urlopen(f'http://127.0.0.1:{port}'+original['download_url'],timeout=10) as r:data=r.read()
                probes.append(kinds==['image','image','video'] and data==(ROOT/'tests/fixtures/whatsapp-video.mp4').read_bytes() and identity(port)['release_id'].endswith(':video-preview-v1'))
    if len(probes)==2:
        facts['visual-input']=test.returncode==0 and all(probes)
        facts['tests-activation']=test.returncode==0 and all(probes)
    after=identity(8118)
    result={'observations':facts,'target_before':before,'target_after':after}
    (OUT/'check-evidence.json').write_text(json.dumps(result,indent=2))
    print('NIENFOS_OBSERVATIONS_V1 '+json.dumps(result))
    return 0 if len(facts)==4 and all(facts.values()) and before==after else 1

if __name__=='__main__':raise SystemExit(main())
