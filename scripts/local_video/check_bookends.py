"""Executed media checks for complete local tutorials; no external semantic service."""
from pathlib import Path
import json,subprocess,sys,tempfile,wave,hashlib
import av,numpy as np
from scipy.signal import correlate
import bookends as b
import voice
ROOT=b.ROOT;OUT=ROOT/'reports/rd-video-completo-20260929';BODY=ROOT/'reports/rd-video-local-v3-20260929'
facts={};metrics={}
def fact(k,v):facts[k]=bool(v);assert v,k

def hashes(path):
    r=subprocess.run([b.FF,'-v','error','-i',str(path),'-map','0:v:0','-f','framemd5','-'],capture_output=True,text=True,check=True)
    return [x.split(',')[-1].strip() for x in r.stdout.splitlines() if x and not x.startswith('#')]
def pcm(path):
    r=subprocess.run([b.FF,'-v','error','-i',str(path),'-vn','-ar','8000','-ac','1','-f','f32le','-'],capture_output=True,check=True)
    return np.frombuffer(r.stdout,dtype='<f4')

def main():
    # Recheck the inherited actual capture, action images, pace and speech placement.
    old=subprocess.run([sys.executable,str(ROOT/'scripts/local_video/check_calm.py')],capture_output=True,text=True,check=True,timeout=120)
    inherited=json.loads(next(x.split(' ',1)[1] for x in old.stdout.splitlines() if x.startswith('NIENFOS_OBSERVATIONS_V1 ')))['observations']
    facts.update(inherited)
    meta=json.loads((OUT/'render.json').read_text());cfg=meta['config'];movie=OUT/'rd-documentos-completo.mp4'
    original=hashes(BODY/'rd-documentos.mp4');complete=hashes(movie);start=meta['intro_frames']
    same=original==complete[start:start+len(original)]
    approved=b.read_pcm(BODY/'aligned-narration.wav');assembled=b.read_pcm(OUT/'narracion.wav');at=start*1600
    same_pcm=np.array_equal(approved,assembled[at:at+len(approved)])
    with av.open(str(movie)) as c:
        v=c.streams.video[0];a=c.streams.audio[0];duration=float(v.duration*v.time_base)
        assert abs(duration-float(a.duration*a.time_base))<.05
        assert v.frames==len(complete) and v.codec_context.name=='h264' and a.codec_context.name=='aac'
    assert b.sha(BODY/'rd-documentos.mp4')==meta['body_sha256']
    assert b.sha(movie)==meta['video_sha256']
    shifts=[n['video_seconds']-o['video_seconds'] for n,o in zip(meta['cues'],json.loads((BODY/'render.json').read_text())['cues'])]
    audio=pcm(movie);reference=pcm(OUT/'narracion.wav');errors=[]
    for t in [meta['audio_offsets_samples']['intro']/48000,meta['body_start']+1.4,meta['body_start']+21,meta['body_start']+35,meta['audio_offsets_samples']['outro']/48000]:
        offset=round(t*8000);ref=reference[offset:offset+16000];low=max(0,offset-800)
        match=low+int(np.argmax(correlate(audio[low:offset+16800],ref,mode='valid',method='fft')))
        errors.append(abs(match-offset)/8000)
    fact('speech-action-sync',inherited['speech-action-sync'] and same and max(abs(x-meta['body_start']) for x in shifts)<1e-8 and max(errors)<.05)
    fact('natural-pauses',inherited['natural-pauses'] and same_pcm)
    fact('calm-pace',same and 40<=meta['body_seconds']<=45 and duration<=60)
    fact('rd-demo-video',inherited['rd-demo-video'] and same)
    fact('fluid-motion',inherited['fluid-motion'] and same)
    provenance=json.loads((ROOT/'scripts/local_video/assets/brand/provenance.json').read_text())
    logos_ok=all(b.sha(ROOT/'scripts/local_video/assets/brand'/x['file'])==x['sha256'] for x in provenance)
    visual=json.loads((OUT/'visual-review.json').read_text())
    fact('closing-brands',logos_ok and same and visual['reviewed_video_sha256']==b.sha(movie) and visual['closing_logos_legible'] and visual['intro_and_end_inspected'])
    narration=json.loads((OUT/'audio/narration.json').read_text())
    fact('voice-default',inherited['voice-default'] and narration['profile']=='voz-1' and all(b.sha(OUT/'audio'/e['deliverable'])==e['metadata']['wav_sha256'] for e in narration['entries']))
    fact('complete-bookends',duration<60 and duration>meta['body_seconds']+6 and len(complete)==sum(meta[k] for k in ['intro_frames','body_frames','outro_frames']) and bool(cfg['title'] and cfg['cta']) and same_pcm)
    with tempfile.TemporaryDirectory(prefix='bookends-check-') as temp:
        temp=Path(temp)
        historical=temp/'historical.json';historical.write_text(json.dumps({**cfg,'instant_intro':cfg.get('instant_intro',False)}))
        r=subprocess.run([sys.executable,str(ROOT/'scripts/local_video/bookends.py'),'--config',str(historical),'--output',str(temp/'replay')],capture_output=True,text=True,check=True,timeout=120)
        repeat=json.loads((temp/'replay/render.json').read_text());rn=json.loads((temp/'replay/audio/narration.json').read_text())
        reused=all(e['cache_hit'] and b.sha(temp/'replay/audio'/e['deliverable'])==e['metadata']['wav_sha256'] for e in rn['entries'])
        fact('reuse-audio',same_pcm and reused)
        assert hashes(temp/'replay/rd-documentos-completo.mp4')==complete
        changed={**cfg,'client':'CLIENTE DE PRUEBA','title':'Otra función','cta':'Probá el nuevo recorrido.','client_logo':cfg['studio_logo']}
        assert b.card(changed,'intro').tobytes()!=b.card(cfg,'intro').tobytes()
        assert b.card(changed,'outro').tobytes()!=b.card(cfg,'outro').tobytes()
        bad=temp/'oversize.json';bad.write_text(json.dumps({**cfg,'minimum_card_seconds':20}))
        rejection=subprocess.run([sys.executable,str(ROOT/'scripts/local_video/bookends.py'),'--config',str(bad),'--output',str(temp/'invalid')],capture_output=True,text=True,timeout=10)
        fact('reusable-bookends',repeat['duration']==meta['duration'] and reused and rejection.returncode!=0 and 'exceeds maximum' in rejection.stderr and not (temp/'invalid').exists() and inherited['v2-delivery'])
        metrics['repeat_render_seconds']=repeat['render_seconds']
    fact('local-render',inherited['local-render'] and narration['network_policy']=='denied' and meta['model_api_integration']=='none')
    fact('evidence-costs',meta['render_seconds']>0 and 'Codex' in (OUT/'README.md').read_text())
    metrics.update(duration=duration,body_frames_identical=len(original),body_pcm_identical=same_pcm,maximum_audio_offset_seconds=max(errors),new_audio_cache_hits=2,criteria_passed=sum(facts.values()),target=str(movie.relative_to(ROOT)))
    print(json.dumps(metrics,ensure_ascii=False))
try:main()
finally:print('NIENFOS_OBSERVATIONS_V1 '+json.dumps({'observations':facts}))
