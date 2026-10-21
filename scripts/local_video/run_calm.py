"""Make a calm 44-second edition from an approved local capture, without resynthesizing."""
from pathlib import Path
import argparse,hashlib,json,shutil,subprocess,sys,time
ROOT=Path(__file__).resolve().parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
source=a.source.resolve();out=a.output.resolve();assert source!=out,'Preserve the approved source version'
started=time.perf_counter();narration=json.loads((source/'audio/narration.json').read_text())
assert narration['profile']=='voz-1'
assert json.loads((source/'capture/capture.json').read_text())['environment']=='local'
out.mkdir(parents=True,exist_ok=True)
for folder in ('capture','audio'):shutil.copytree(source/folder,out/folder,dirs_exist_ok=True)
shutil.copyfile(source/'alignment.json',out/'alignment.json')
for entry in narration['entries']:
    assert hashlib.sha256((out/'audio'/entry['deliverable']).read_bytes()).hexdigest()==entry['metadata']['wav_sha256']
subprocess.run([sys.executable,str(ROOT/'render_v2.py'),'--calm','--output',str(out)],check=True)
(out/'run.json').write_text(json.dumps({'edition':3,'completed':True,'seconds':time.perf_counter()-started,
    'reuse_capture':True,'reuse_audio':True,'tts_calls':0,'model_api_integration':'none','voice':'voz-1'},indent=2)+'\n')
