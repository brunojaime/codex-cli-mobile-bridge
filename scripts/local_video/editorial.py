"""Compact local editorial brief and strict Codex-authored pacing plan. No inference."""
from pathlib import Path
import argparse,hashlib,json,math,wave
import numpy as np
import pacing
from bookends import read_pcm
ROOT=Path(__file__).resolve().parent

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def recipe():return json.loads((ROOT/'rd-documents.json').read_text())
def input_digest(source):
    files=[ROOT/'rd-documents.json',source/'alignment.json',source/'capture/capture.json']
    for s in recipe()['scenes']:files += [source/'audio'/f"{s['id']}.wav",source/'capture'/s['id']/'frames.json']
    return hashlib.sha256(json.dumps([sha(p) for p in files]).encode()).hexdigest()
def silence_spans(samples,sr=48000):
    hop=sr//100;x=samples[:len(samples)//hop*hop].astype(float).reshape(-1,hop)/32768
    quiet=np.sqrt(np.mean(x*x,axis=1))<10**(-45/20);spans=[];begin=None
    for i,value in enumerate(list(quiet)+[False]):
        if value and begin is None:begin=i
        if not value and begin is not None:
            if i-begin>=30:spans.append({'start':round(begin*.01,2),'seconds':round((i-begin)*.01,2)})
            begin=None
    return spans

def brief(source):
    source=Path(source);meta=json.loads((source/'render.json').read_text());r=recipe();scenes=[]
    spans=silence_spans(read_pcm(source/'aligned-narration.wav'))
    for s,t in zip(r['scenes'],meta['timeline']):
        sid=s['id'];pieces=[p for p in meta['audio_segments'] if p['id']==sid]
        lead=pieces[0]['start_sample']/48000-t['start'];tail=t['start']+t['duration']-(pieces[-1]['start_sample']+pieces[-1]['sample_count'])/48000
        pauses=[{'after_speech_seconds':a['source_end_seconds'],'seconds':round((b['start_sample']-a['start_sample']-a['sample_count'])/48000,3)} for a,b in zip(pieces,pieces[1:])]
        scenes.append({'id':sid,'title':s['title'],'speech':s['text'],'speech_seconds':t['speech_seconds'],'screen_seconds':round(t['duration'],3),'lead_seconds':round(lead,3),'tail_seconds':round(tail,3),'pauses':pauses,'actions':[{'id':c['id'],'speech_at':c['speech_seconds'],'screen_at':round(c['scene_seconds'],3)} for c in meta['cues'] if c['scene']==sid]})
    return {'version':1,'input_digest':input_digest(source),'body_seconds':round(meta['duration'],3),'voice':'voz-1','scenes':scenes,'silences_over_0_3_seconds':spans,'transition_waits':[{'from':a['id'],'to':b['id'],'scheduled_seconds':round(a['tail_seconds']+b['lead_seconds'],3)} for a,b in zip(scenes,scenes[1:])],'instructions':'Codex: justify per-scene lead/tail and per-cut pause. Preserve voice rate, approved cut positions, readable captions and under 60 s total. No model is called by render.'}

def number(x,lo,hi):
    if isinstance(x,bool) or not isinstance(x,(float,int)) or not math.isfinite(x) or not lo<=x<=hi:raise ValueError(f'Timing outside {lo}..{hi}')
    return float(x)
def load_plan(path,source):
    data=json.loads(Path(path).read_text());expected={'version','input_digest','editor','scenes'}
    if set(data)!=expected or data['version']!=1 or data['editor']!='Codex':raise ValueError('Invalid pacing plan schema')
    if data['input_digest']!=input_digest(Path(source)):raise ValueError('Stale pacing plan: capture, speech or alignment changed')
    if set(data['scenes'])!=set(pacing.PAUSES):raise ValueError('Plan must cover every scene exactly')
    for sid,s in data['scenes'].items():
        if set(s)!={'lead_seconds','tail_seconds','pauses','reason'} or not isinstance(s['reason'],str) or not s['reason'].strip():raise ValueError('Timing requires an editorial reason')
        number(s['lead_seconds'],.35,2.5);number(s['tail_seconds'],.5,4)
        if len(s['pauses'])!=len(pacing.PAUSES[sid]):raise ValueError('Use the approved speech boundaries')
        for p,(cut,_) in zip(s['pauses'],pacing.PAUSES[sid]):
            if set(p)!={'after_speech_seconds','seconds'} or p['after_speech_seconds']!=cut:raise ValueError('Do not move speech cuts without a new alignment review')
            number(p['seconds'],.25,2.5)
    return data

def at(plan,sid,t):
    s=plan['scenes'][sid];return s['lead_seconds']+t+sum(p['seconds'] for p in s['pauses'] if p['after_speech_seconds']<=t+1e-8)
def intervals(plan,sid,duration):
    points=[0]+[p['after_speech_seconds'] for p in plan['scenes'][sid]['pauses']]+[duration]
    return [(a,b,at(plan,sid,a)) for a,b in zip(points,points[1:])]
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    data=brief(a.source);text=json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n';a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(text)
    print(json.dumps({'characters':len(text),'utf8_bytes':len(text.encode()),'path':str(a.output),'token_count':'not measured'}))
