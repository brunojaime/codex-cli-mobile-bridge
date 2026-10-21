"""Verify optional music against real MP4 and separated PCM, plus deterministic replays."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys,tempfile
import av,numpy as np
from scipy.signal import correlate
import bookends as b,music,guide_qc as q
ROOT=b.ROOT;OUT=ROOT/'reports/rd-video-musica-20260929';SOURCE=ROOT/'reports/rd-video-editorial-20260929'
facts={};metrics={}
def fact(k,v):facts[k]=bool(v);assert v,k

def video_hash(p):
 with av.open(str(p)) as c:
  h=hashlib.sha256();timestamps=[]
  for pkt in c.demux(video=0):
   if pkt.size:h.update(bytes(pkt));timestamps.append((float(pkt.pts*pkt.time_base),float(pkt.duration*pkt.time_base)))
 return h.hexdigest(),timestamps

def decoded_audio(p):
 r=subprocess.run([b.FF,'-v','error','-i',str(p),'-vn','-ar','48000','-ac','1','-f','f32le','-'],capture_output=True,check=True);return np.frombuffer(r.stdout,dtype='<f4')

def main():
 p=argparse.ArgumentParser();p.add_argument('--focused',action='store_true');args=p.parse_args()
 if not args.focused:
  r=subprocess.run([sys.executable,str(ROOT/'scripts/local_video/check_editorial.py')],capture_output=True,text=True,check=True,timeout=240)
  facts.update(json.loads(next(x.split(' ',1)[1] for x in r.stdout.splitlines() if x.startswith('NIENFOS_OBSERVATIONS_V1 ')))['observations'])
 dry=b.read_pcm(OUT/'narracion.wav');bed=b.read_pcm(OUT/'musica.wav');mixed=b.read_pcm(OUT/'mezcla.wav');info=json.loads((OUT/'music.json').read_text())
 cfg=music.validate(json.loads((OUT/'music-plan.json').read_text()));assert np.array_equal(dry,b.read_pcm(SOURCE/'narracion.wav'))
 assert np.array_equal(mixed.astype(np.int32)-bed.astype(np.int32),dry.astype(np.int32))
 exact=video_hash(OUT/'rd-documentos-completo.mp4')==video_hash(SOURCE/'rd-documentos-completo.mp4');assert exact
 actual=decoded_audio(OUT/'rd-documentos-completo.mp4');assert np.abs(actual).max()<.999
 with av.open(str(OUT/'rd-documentos-completo.mp4')) as c:
  v=c.streams.video[0];a=c.streams.audio[0];duration=float(v.duration*v.time_base)
  assert abs(duration-float(a.duration*a.time_base))<.05 and v.codec_context.name=='h264' and a.codec_context.name=='aac'
  assert q.first_frame_ok(next(c.decode(video=0)).to_image())
 assert q.inspect(OUT,write=False)['checks']['captions_readable']
 fact('optional-ambient-music',exact and np.sqrt(np.mean(bed.astype(float)**2))>10 and duration==info['duration']<60 and b.sha(OUT/'subtitulos.srt')==b.sha(SOURCE/'subtitulos.srt') and SOURCE.joinpath('rd-documentos-completo.mp4').exists())
 # Recover the applied envelope against the deterministic raw pad, in 100 ms windows.
 raw=music.pad(len(bed),48000);width=4800;n=len(bed)//width
 a=raw[:n*width].reshape(n,width);y=bed[:n*width].astype(float).reshape(n,width)/32768
 gains=np.sum(a*y,axis=1)/np.sum(a*a,axis=1);times=np.arange(n)*.1
 middle=gains[(times>2)&(times<duration-2)]
 expected=info['base_music_rms']*10**(-cfg['duck_db']/20)
 assert np.max(np.abs(middle-expected))<2e-6,'Music rises during reading pauses'
 assert np.abs(bed[:4800].astype(float)).max()<np.abs(bed[2*48000:3*48000].astype(float)).max()*.1
 assert np.abs(bed[-4800:].astype(float)).max()<np.abs(bed[2*48000:3*48000].astype(float)).max()*.1
 # Check actual AAC contains the planned mix without timing drift.
 errors=[];correlations=[]
 ref=mixed.astype(float)/32768
 for sec in [1,6,13,22,30,37]:
  start=round(sec*48000);part=ref[start:start+48000];lo=max(0,start-2400)
  match=lo+int(np.argmax(correlate(actual[lo:start+50400],part,mode='valid',method='fft')))
  errors.append(abs(match-start)/48000);correlations.append(float(np.corrcoef(part,actual[match:match+len(part)])[0,1]))
 fact('voice-first-mix',info['music_rms_db_relative_to_active_voice']<-24 and info['mixed_peak']<.97 and max(errors)<.005 and min(correlations)>.99)
 with tempfile.TemporaryDirectory(prefix='rd-music-check-') as temp:
  temp=Path(temp)
  for mode in ['soft-ambient','none']:
   plan=temp/f'{mode}.json';plan.write_text(json.dumps({**cfg,'mode':mode}))
   result=subprocess.run([sys.executable,str(ROOT/'scripts/local_video/music.py'),'--source',str(SOURCE),'--output',str(temp/mode),'--plan',str(plan)],capture_output=True,text=True,check=True,timeout=40)
   if mode=='soft-ambient':assert b.sha(temp/mode/'mezcla.wav')==b.sha(OUT/'mezcla.wav')
   else:
    assert b.sha(temp/mode/'rd-documentos-completo.mp4')==b.sha(SOURCE/'rd-documentos-completo.mp4')
    assert np.count_nonzero(b.read_pcm(temp/mode/'musica.wav'))==0
  invalid=temp/'invalid.json';invalid.write_text(json.dumps({**cfg,'level_db_below_voice':-10}))
  r=subprocess.run([sys.executable,str(ROOT/'scripts/local_video/music.py'),'--source',str(SOURCE),'--output',str(temp/'bad'),'--plan',str(invalid)],capture_output=True,text=True)
  assert r.returncode!=0 and not (temp/'bad').exists()
  if not args.focused:
   subprocess.run([sys.executable,str(ROOT/'scripts/local_video/run_guided.py'),'--source',str(ROOT/'reports/rd-video-guia-20260929/body'),'--pacing-plan',str(SOURCE/'pacing-plan.json'),'--music-plan',str(OUT/'music-plan.json'),'--output',str(temp/'integrated')],capture_output=True,text=True,check=True,timeout=140)
   assert b.sha(temp/'integrated/con-musica/mezcla.wav')==b.sha(OUT/'mezcla.wav')
   assert (temp/'integrated/rd-documentos-completo.mp4').exists()
 for rel in ['SKILL.md','music.md','pacing.md','agents/openai.yaml']:
  assert b.sha(Path.home()/'.codex/skills/local-feature-videos'/rel)==b.sha(ROOT/'scripts/local_video/skill/local-feature-videos'/rel)
 subprocess.run([str(ROOT/'.venv/bin/python'),str(Path.home()/'.codex/skills/.system/skill-creator/scripts/quick_validate.py'),str(Path.home()/'.codex/skills/local-feature-videos')],capture_output=True,check=True)
 fact('reusable-music-option',info['tts_calls']==info['model_api_calls']==0 and cfg['mode']=='soft-ambient')
 # Inherited narration timing and silence checks apply to the isolated, identical voice track.
 if not args.focused:
  assert exact and b.sha(OUT/'narracion.wav')==b.sha(SOURCE/'narracion.wav')
 metrics.update(duration=duration,video_packets_and_timestamps_identical=exact,voice_component_identical=True,music_relative_db=info['music_rms_db_relative_to_active_voice'],decoded_audio_peak=float(np.abs(actual).max()),max_audio_offset_seconds=max(errors),min_audio_correlation=min(correlations),constant_midsection_gain_error=float(np.max(np.abs(middle-expected))),criteria_passed=sum(facts.values()),target=str((OUT/'rd-documentos-completo.mp4').relative_to(ROOT)))
 print(json.dumps(metrics))
try:main()
finally:print('NIENFOS_OBSERVATIONS_V1 '+json.dumps({'observations':facts}))
