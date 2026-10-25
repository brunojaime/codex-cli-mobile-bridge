"""Optional local intelligibility check; does not judge accent or naturalness."""
from pathlib import Path
import json, os, sys
os.environ['HF_HUB_OFFLINE']='1'
from faster_whisper import WhisperModel
out=Path(sys.argv[1]); recipe=json.loads((Path(__file__).parent/'rd-documents.json').read_text())
model=WhisperModel('small',device='cpu',compute_type='int8',cpu_threads=2,num_workers=1,local_files_only=True)
results=[]
for scene in recipe['scenes']:
    segments,_=model.transcribe(str(out/'audio'/f'{scene["id"]}.wav'),language='es',beam_size=5)
    result={'id':scene['id'],'expected':scene['text'],'transcription':' '.join(s.text.strip() for s in segments)}
    results.append(result); print(json.dumps(result,ensure_ascii=False),flush=True)
(out/'transcription.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
