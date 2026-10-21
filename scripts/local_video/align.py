"""Local word timing for cached narration; no LLM or model API."""
from pathlib import Path
import argparse, hashlib, json, os, sys
ROOT=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output; narration=json.loads((out/'audio/narration.json').read_text())
    key=hashlib.sha256(json.dumps([e['metadata']['wav_sha256'] for e in narration['entries']]).encode()).hexdigest()
    target=out/'alignment.json'
    if target.exists() and json.loads(target.read_text()).get('audio_digest')==key:
        print('Word timing: cache hit');return
    os.environ['HF_HUB_OFFLINE']='1'
    def offline(event,values):
        if event in ('socket.connect','socket.getaddrinfo'):raise RuntimeError('Alignment must run offline')
    sys.addaudithook(offline)
    from faster_whisper import WhisperModel
    model=WhisperModel('small',device='cpu',compute_type='int8',cpu_threads=2,num_workers=1,local_files_only=True)
    scenes=[]
    for entry in narration['entries']:
        segments,_=model.transcribe(str(out/'audio'/entry['deliverable']),language='es',beam_size=5,word_timestamps=True)
        words=[{'word':w.word.strip(),'start':w.start,'end':w.end} for s in segments for w in s.words]
        scenes.append({'id':entry['id'],'words':words,'audio_sha256':entry['metadata']['wav_sha256']})
        print(entry['id'],json.dumps(words,ensure_ascii=False),flush=True)
    target.write_text(json.dumps({'audio_digest':key,'method':'faster-whisper small CPU int8 local; approximate word times','scenes':scenes},ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':main()
