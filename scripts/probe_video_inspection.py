#!/usr/bin/env python3
"""One identified synthetic upload per environment; preserve uncertain attempts."""
import json
from pathlib import Path
import sys
import urllib.request

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from services.whatsapp_ingest.worker import encode_multipart_form
OUT=ROOT/'reports/whatsapp-video-inspection-20261005'

def request(base,path,data=None):
    req=urllib.request.Request(base+path,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=45) as r:return json.load(r)

def main(env):
    base='http://127.0.0.1:'+('8000' if env=='prod' else '8118')
    assert request(base,'/health')['features'].get('video_preview_v1'), 'Backend not activated'
    path=OUT/f'{env}-probe.json'
    state=json.loads(path.read_text()) if path.exists() else {}
    if not state.get('session_id'):
        state['session_id']=request(base,'/sessions',{'title':'Prueba técnica · inspección video V1 · '+env,'workspace_path':str(ROOT)})['id']
        path.write_text(json.dumps(state,indent=2))
    if not state.get('job_id'):
        if state.get('upload_started'):raise RuntimeError('Uncertain attempt; inspect before retry')
        state['upload_started']=True;path.write_text(json.dumps(state,indent=2))
        boundary='video-native-preview-v1'
        body=encode_multipart_form(boundary,{'session_id':state['session_id'],'message':'PRUEBA INSPECCIÓN VIDEO V1. No modificar archivos ni usar herramientas. Describir sólo el color visible en las imágenes adjuntas. Es un video sintético de prueba, no hay pedido de implementar.'},[ROOT/'tests/fixtures/whatsapp-video.mp4'])
        req=urllib.request.Request(base+'/message/attachments',data=body,headers={'Content-Type':f'multipart/form-data; boundary={boundary}'})
        with urllib.request.urlopen(req,timeout=45) as r:state['job_id']=json.load(r)['job_id']
        path.write_text(json.dumps(state,indent=2))
    session=request(base,'/sessions/'+state['session_id'])
    user=next(m for m in session['messages'] if m['role']=='user')
    assert [a['kind'] for a in user['attachments']]==['image','image','video']
    import hashlib
    hashes=[]
    for attachment in user['attachments']:
        with urllib.request.urlopen(base+attachment['download_url'],timeout=15) as r:data=r.read()
        hashes.append(hashlib.sha256(data).hexdigest())
    assert hashes[-1]==hashlib.sha256((ROOT/'tests/fixtures/whatsapp-video.mp4').read_bytes()).hexdigest()
    state.update(verified_native_images=2,original_bytes_match=True,download_sha256=hashes)
    path.write_text(json.dumps(state,indent=2));print(json.dumps(state))

if __name__=='__main__':main(sys.argv[1])
