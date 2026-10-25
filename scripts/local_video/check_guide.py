"""Acceptance evidence for first frame, calmer visual guidance and local editorial QC."""
from pathlib import Path
import json,subprocess,sys,tempfile
import av,numpy as np
from PIL import Image
from scipy.signal import correlate
import bookends as b
import guide_qc as q
ROOT=b.ROOT;OUT=ROOT/'reports/rd-video-guia-20260929';OLD=ROOT/'reports/rd-video-completo-20260929';SOURCE=ROOT/'reports/rd-video-local-v3-20260929'
facts={};metrics={}
def fact(k,v):facts[k]=bool(v);assert v,k

def first(p):
    with av.open(str(p)) as c:return next(c.decode(video=0)).to_image()
def decoded(p,filter):
    r=subprocess.run([b.FF,'-v','error','-i',str(p),'-vf',filter,'-pix_fmt','rgb24','-f','rawvideo','-'],capture_output=True,check=True)
    return np.frombuffer(r.stdout,dtype=np.uint8)
def pcm(p):
    r=subprocess.run([b.FF,'-v','error','-i',str(p),'-vn','-ac','1','-ar','8000','-f','f32le','-'],capture_output=True,check=True)
    return np.frombuffer(r.stdout,dtype='<f4')

def main():
    previous=subprocess.run([sys.executable,str(ROOT/'scripts/local_video/check_bookends.py')],capture_output=True,text=True,check=True,timeout=160)
    inherited=json.loads(next(x.split(' ',1)[1] for x in previous.stdout.splitlines() if x.startswith('NIENFOS_OBSERVATIONS_V1 ')))['observations']
    facts.update(inherited)
    meta=json.loads((OUT/'render.json').read_text());old=json.loads((OLD/'render.json').read_text());movie=OUT/'rd-documentos-completo.mp4'
    guided=json.loads((OUT/'body/render.json').read_text());approved=json.loads((SOURCE/'render.json').read_text())
    assert guided['timeline']==approved['timeline'] and guided['cues']==approved['cues']
    newframes=decoded(OUT/'body/rd-documentos.mp4','crop=584:978:68:99,scale=146:245').reshape(-1,245,146,3)
    oldframes=decoded(SOURCE/'rd-documentos.mp4','crop=584:978:68:99,scale=146:245').reshape(-1,245,146,3)
    errors=np.abs(newframes.astype(float)-oldframes.astype(float)).mean(axis=(1,2,3));assert len(errors)==1315 and max(errors)<1.5
    same_audio=b.sha(OUT/'narracion.wav')==b.sha(OLD/'narracion.wav')
    fact('natural-pauses',inherited['natural-pauses'] and same_audio)
    fact('calm-pace',meta['duration']==old['duration'] and meta['body_seconds']==old['body_seconds'] and max(errors)<1.5)
    fact('rd-demo-video',inherited['rd-demo-video'] and max(errors)<1.5)
    fact('fluid-motion',inherited['fluid-motion'] and guided['timeline']==approved['timeline'])
    actual=pcm(movie);ref=pcm(OUT/'narracion.wav');offsets=[]
    for t in [1,5,16,27,40,48]:
        center=round(t*8000);part=ref[center:center+16000];lo=max(0,center-800)
        position=lo+int(np.argmax(correlate(actual[lo:center+16800],part,mode='valid',method='fft')))
        offsets.append(abs(position-center)/8000)
    fact('speech-action-sync',meta['cues']==old['cues'] and max(offsets)<.05)
    with av.open(str(movie)) as c:
        v=c.streams.video[0];a=c.streams.audio[0];assert abs(float(v.duration*v.time_base)-float(a.duration*a.time_base))<.05
    review=json.loads((OUT/'visual-review.json').read_text());assert review['video_sha256']==b.sha(movie) and review['inspected']
    now=first(movie);before=first(OLD/'rd-documentos-completo.mp4')
    fact('visible-first-frame',q.first_frame_ok(now) and not q.first_frame_ok(before) and (OUT/'portada.jpg').exists() and review['first_frame_title_legible'])
    a=q.captions(SOURCE/'subtitulos.srt');n=q.captions(OUT/'body/subtitulos.srt')
    assert [x['text'] for x in a]==[x['text'] for x in n]
    coverage_old=sum(x['end']-x['start'] for x in a);coverage_new=sum(x['end']-x['start'] for x in n)
    assert all(x['end']-x['start']>=y['end']-y['start'] for x,y in zip(n,a))
    # Observe actual pixels in the subtitle band during every end-of-step reading pause.
    caption_present=[];progress=[]
    with av.open(str(OUT/'body/rd-documentos.mp4')) as c:
        targets={round((s['start']+s['duration']-.6)*30) for s in guided['timeline']}
        for i,f in enumerate(c.decode(video=0)):
            if i in targets:
                rgb=f.to_ndarray(format='rgb24');caption_present.append(int((rgb[1100:1180].min(axis=2)>180).sum())>500)
            if i in [60,180]:
                rgb=f.to_ndarray(format='rgb24');progress.append(int((rgb[1212:1216,34:184,1]>150).sum()))
    fact('guide-readability',coverage_new>coverage_old+10 and all(caption_present) and progress[1]>progress[0]+100 and same_audio and review['reading_pauses_inspected'])
    qc=q.inspect(OUT,write=False)
    assert not q.first_frame_ok(Image.new('RGB',(720,1280),'white'))
    assert not q.caption_checks([{'start':0,'end':2,'text':'Texto'},{'start':1,'end':3,'text':'Otro'}],4)['ordered']
    assert not q.caption_checks([{'start':0,'end':.2,'text':'Texto demasiado rápido para leer'}],4)['readable']
    assert not q.audio_checks(np.zeros(48000*7,dtype=np.int16))['valid']
    assert not q.audio_checks(np.full(48000,32767,dtype=np.int16))['valid']
    with tempfile.TemporaryDirectory(prefix='rd-guide-repeat-') as temp:
        r=subprocess.run([sys.executable,str(ROOT/'scripts/local_video/run_guided.py'),'--output',temp],capture_output=True,text=True,check=True,timeout=160)
        temp=Path(temp);run=json.loads((temp/'run.json').read_text());rn=json.loads((temp/'audio/narration.json').read_text())
        assert b.sha(temp/'narracion.wav')==b.sha(OUT/'narracion.wav')
        assert all(x['cache_hit'] for x in rn['entries']) and run['tts_calls']==0
        assert q.inspect(temp,write=False)['checks']==qc['checks']
        assert first(temp/'rd-documentos-completo.mp4').tobytes()==now.tobytes()
        metrics['repeat_seconds']=run['seconds']
    fact('reuse-audio',same_audio and run['tts_calls']==0 and all(x['cache_hit'] for x in rn['entries']))
    fact('local-render',inherited['local-render'] and run['model_api_calls']==0)
    fact('automatic-guide-qc',all(qc['checks'].values()) and run['tts_calls']==0)
    fact('complete-bookends',inherited['complete-bookends'] and meta['duration']==old['duration'] and meta['config']['title']==old['config']['title'] and meta['config']['cta']==old['config']['cta'])
    fact('closing-brands',inherited['closing-brands'] and b.sha(OUT/'outro.png')==b.sha(OLD/'outro.png') and review['closing_unchanged'])
    fact('reusable-bookends',inherited['reusable-bookends'] and q.first_frame_ok(now))
    fact('evidence-costs',(OUT/'README.md').exists() and 'Codex' in (OUT/'README.md').read_text() and qc['duration']<60)
    metrics.update(duration=meta['duration'],caption_visible_seconds_before=coverage_old,caption_visible_seconds_after=coverage_new,maximum_viewport_pixel_error=float(max(errors)),audio_pcm_identical=same_audio,maximum_audio_offset_seconds=max(offsets),negative_qc_cases_rejected=5,criteria_passed=sum(facts.values()),target=str(movie.relative_to(ROOT)))
    print(json.dumps(metrics))
try:main()
finally:print('NIENFOS_OBSERVATIONS_V1 '+json.dumps({'observations':facts}))
