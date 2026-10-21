"""Incremental offline word timing and transcription comparison for the new RD narration."""
from pathlib import Path
import argparse, difflib, json, os, re, sys, time, unicodedata
from bookends import sha
from rd_full_render import RECIPE

def normalized(text):
    return re.sub(r'[^a-z0-9 ]','',unicodedata.normalize('NFKD',text.lower())).split()

def main():
    p=argparse.ArgumentParser();p.add_argument('--folder',type=Path,required=True);p.add_argument('--watch',action='store_true');a=p.parse_args()
    os.environ.update(HF_HUB_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
    def offline(event,values):
        if event in ('socket.connect','socket.getaddrinfo'):raise RuntimeError('Offline alignment blocks network')
    sys.addaudithook(offline)
    from faster_whisper import WhisperModel
    model=WhisperModel('small',device='cpu',compute_type='int8',cpu_threads=1,num_workers=1,local_files_only=True)
    recipe=json.loads(RECIPE.read_text())['scenes'];target=a.folder/'alignment.json'
    existing=json.loads(target.read_text())['scenes'] if target.exists() else []
    results={s['id']:s for s in existing};deadline=time.monotonic()+7200
    while len(results)<len(recipe):
        for scene in recipe:
            path=a.folder/'audio'/f"{scene['id']}.wav"
            if not path.exists():continue
            digest=sha(path)
            if scene['id'] in results and results[scene['id']]['audio_sha256']==digest:continue
            segments,_=model.transcribe(str(path),language='es',beam_size=5,word_timestamps=True)
            words=[{'word':w.word.strip(),'start':w.start,'end':w.end} for s in segments for w in s.words]
            transcript=' '.join(w['word'] for w in words)
            ratio=difflib.SequenceMatcher(None,normalized(scene['text']),normalized(transcript)).ratio()
            results[scene['id']]={'id':scene['id'],'audio_sha256':digest,'words':words,'transcript':transcript,'script_similarity':ratio}
            target.write_text(json.dumps({'method':'faster-whisper small CPU int8 offline; approximate times, not human listening','scenes':[results[s['id']] for s in recipe if s['id'] in results]},ensure_ascii=False,indent=2)+'\n')
            print(scene['id'],round(ratio,3),transcript,flush=True)
        if not a.watch or time.monotonic()>deadline:break
        if len(results)<len(recipe):time.sleep(10)
    if len(results)!=len(recipe):raise RuntimeError('Narration incomplete')

if __name__=='__main__':main()
