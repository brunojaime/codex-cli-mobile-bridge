from pathlib import Path
import difflib,json,os,re,unicodedata
os.environ['HF_HUB_OFFLINE']='1'
from faster_whisper import WhisperModel
root=Path(__file__).resolve().parents[3]
out=root/'reports/videos/nienfos-v20-crecer'
expected=json.loads((out/'timing.json').read_text())['text']
model=WhisperModel('small',device='cpu',compute_type='int8',cpu_threads=2,num_workers=1,local_files_only=True)
segments,_=model.transcribe(str(out/'locucion.mp3'),language='es',beam_size=5)
items=[{'start':s.start,'end':s.end,'text':s.text.strip()} for s in segments]
actual=' '.join(s['text'] for s in items)
def normalize(s):
    return re.sub(r'[^a-z0-9 ]','',unicodedata.normalize('NFD',s.lower()).encode('ascii','ignore').decode())
ratio=difflib.SequenceMatcher(None,normalize(expected),normalize(actual)).ratio()
result={'expected':expected,'transcribed':actual,'similarity':ratio,'segments':items,'scope':'Local intelligibility check; does not certify naturalness or accent'}
(out/'transcription-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False))
