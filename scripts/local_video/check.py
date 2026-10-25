"""Executable evidence for the RD tutorial deliverable; no remote evaluator."""
from pathlib import Path
import difflib, json, subprocess, sys, tempfile, time, unicodedata, wave
import av
import numpy as np
from PIL import Image, ImageChops, ImageStat
import imageio_ffmpeg
import voice
ROOT=Path(__file__).resolve().parent
OUT=ROOT.parents[1]/'reports/rd-video-local-20260929'
observations={}
def fact(name,value):
    observations[name]=bool(value)
    assert value,name

def main():
    recipe=json.loads((ROOT/'rd-documents.json').read_text())
    settings=json.loads((ROOT/'voices.json').read_text())
    narration=json.loads((OUT/'audio/narration.json').read_text())
    fact('voice-default',voice.profile()[0]=='voz-1' and voice.profile(True)[0]=='peter-fast'
         and settings['fast_requires_explicit_request'] and narration['profile']=='voz-1'
         and voice.sha(ROOT/settings['profiles']['voz-1']['reference'])==voice.sha(ROOT.parents[1]/'reports/argentina-local-20260929/references/arm_06136.wav'))
    with tempfile.TemporaryDirectory(prefix='rd-video-check-') as temp:
        temp=Path(temp); before={e['path']:Path(e['path']).stat().st_mtime_ns for e in narration['entries']}
        started=time.perf_counter()
        result=subprocess.run([sys.executable,str(ROOT/'voice.py'),str(ROOT/'rd-documents.json'),'--output',str(temp/'audio')],check=True,capture_output=True,text=True,timeout=30)
        repeated=json.loads((temp/'audio/narration.json').read_text())
        cache_seconds=time.perf_counter()-started
        entry=repeated['entries'][0]; corrupt=temp/'corrupt'; corrupt.mkdir()
        (corrupt/f'{entry["key"]}.json').write_text(json.dumps(entry['metadata']))
        (corrupt/f'{entry["key"]}.wav').write_bytes(b'altered audio')
        fact('reuse-audio',all(e['cache_hit'] and voice.sha(temp/'audio'/e['deliverable'])==e['metadata']['wav_sha256'] for e in repeated['entries'])
             and all(Path(path).stat().st_mtime_ns==mtime for path,mtime in before.items())
             and voice.cached(corrupt,entry['key']) is None and 'Synthesizing' not in result.stdout)
    capture=json.loads((OUT/'capture/capture.json').read_text())
    fact('local-render',narration['network_policy']=='denied' and capture['environment']=='local'
         and capture['blocked_external_requests']==0 and capture['mail_provider']=='simulation'
         and "sys.addaudithook(deny_network)" in (ROOT/'voice.py').read_text()
         and "url.hostname, '127.0.0.1'" in (ROOT/'record_rd.mjs').read_text()
         and all(not any(api in (ROOT/name).read_text().lower() for api in ('api.openai.com','api.anthropic.com','openrouter.ai','codex exec')) for name in ('run.py','voice.py','record_rd.mjs','render.py')))
    path=OUT/'rd-documentos.mp4'; container=av.open(str(path))
    v=container.streams.video[0]; a=container.streams.audio[0]
    video_duration=float(v.duration*v.time_base); audio_duration=float(a.duration*a.time_base)
    fact('rd-demo-video',v.codec_context.name=='h264' and a.codec_context.name=='aac'
         and v.width==720 and v.height==1280 and video_duration>20
         and abs(video_duration-audio_duration)<.3 and capture['saved_renewals']==1
         and capture['saved_files']==1 and capture['saved_notices']==1 and not capture['page_errors']
         and all(s['frames']>2 for s in capture['scenes'])
         and len((OUT/'subtitulos.srt').read_text().split('-->'))==5)
    container.close()
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-i',str(path),'-f','null','-'],check=True,capture_output=True,timeout=60)
    # Sample every second: catch missing screen overlays, including DPR changes in screencast.
    container=av.open(str(path)); sampled=[]
    for frame in container.decode(video=0):
        if frame.pts is not None and abs(float(frame.time_base*frame.pts)-round(float(frame.time_base*frame.pts)))<.025:
            crop=frame.to_image().crop((80,110,640,1070)); sampled.append(crop)
    assert len(sampled)>20
    assert all(max(ImageStat.Stat(im.resize((60,100))).var)>100 for im in sampled), 'Blank screen in exported video'
    assert any(ImageChops.difference(sampled[i],sampled[i+1]).getbbox() for i in range(len(sampled)-1))
    container.close()
    for entry in narration['entries']:
        with wave.open(str(OUT/'audio'/entry['deliverable'])) as wav:
            samples=np.frombuffer(wav.readframes(wav.getnframes()),dtype='<i2').astype(float)/32768
            assert len(samples)>24000 and np.sqrt(np.mean(samples*samples))>.005 and np.isfinite(samples).all()
    asr=json.loads((OUT/'transcription.json').read_text())
    def normalized(text): return ''.join(c for c in unicodedata.normalize('NFD',text.lower()) if c.isalnum() or c.isspace())
    coverage=[difflib.SequenceMatcher(None,normalized(r['expected']),normalized(r['transcription'])).ratio() for r in asr]
    metrics=json.loads((OUT/'render.json').read_text())
    fact('evidence-costs',len(asr)==4 and min(coverage)>.8 and metrics['render_seconds']>0
         and all(e['metadata']['synthesis_seconds']>0 for e in narration['entries'])
         and '--reuse-capture' in (ROOT/'README.md').read_text() and 'Codex' in (ROOT/'README.md').read_text())
    print(json.dumps({'cache_reuse_seconds':round(cache_seconds,3),'video_seconds':video_duration,'audio_seconds':audio_duration,'frames_inspected':len(sampled),'asr_text_similarity':coverage,'notice_status':capture['notice_status']},ensure_ascii=False))
try:
    main()
finally:
    print('NIENFOS_OBSERVATIONS_V1 '+json.dumps({'observations':observations}))
