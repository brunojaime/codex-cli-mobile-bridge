"""Executed checks for the modest music lift and recorded-action guidance."""
from pathlib import Path
import argparse,copy,json,subprocess,sys,tempfile
import av,numpy as np
from scipy.signal import correlate
import actions,bookends as b,music,guide_qc as q
ROOT=b.ROOT;OUT=ROOT/'reports/rd-video-acciones-20260929';FINAL=OUT/'final';SOURCE=ROOT/'reports/rd-video-editorial-20260929';OLD=ROOT/'reports/rd-video-b-final-20260929'
facts={}
def fact(k,v):facts[k]=bool(v);assert v,k

def frame_at(path,t):
 with av.open(str(path)) as c:
  for f in c.decode(video=0):
   if f.time>=t:return f.to_image()

def main():
 p=argparse.ArgumentParser();p.add_argument('--focused',action='store_true');args=p.parse_args()
 if not args.focused:
  r=subprocess.run([sys.executable,str(ROOT/'scripts/local_video/check_music_options.py')],capture_output=True,text=True,check=True,timeout=420)
  facts.update(json.loads(next(x.split(' ',1)[1] for x in r.stdout.splitlines() if x.startswith('NIENFOS_OBSERVATIONS_V1 ')))['observations'])
 plan=actions.validate(json.loads((OUT/'actions-plan.json').read_text()),SOURCE)
 oldmeta=json.loads((OLD/'music.json').read_text());meta=json.loads((FINAL/'music.json').read_text());rm=json.loads((FINAL/'render.json').read_text())
 dry=b.read_pcm(FINAL/'narracion.wav');bed=b.read_pcm(FINAL/'musica.wav');mixed=b.read_pcm(FINAL/'mezcla.wav')
 assert np.array_equal(mixed.astype(np.int32)-bed.astype(np.int32),dry.astype(np.int32))
 assert b.sha(FINAL/'narracion.wav')==b.sha(OLD/'narracion.wav')
 assert b.sha(FINAL/'subtitulos.srt')==b.sha(OLD/'subtitulos.srt')
 assert rm['cues']==json.loads((SOURCE/'render.json').read_text())['cues']
 lufs=music.integrated_lufs(bed);previous=music.integrated_lufs(b.read_pcm(OLD/'musica.wav'));increase=lufs-previous
 actual=np.frombuffer(subprocess.check_output([b.FF,'-v','error','-i',str(FINAL/'rd-documentos-completo.mp4'),'-vn','-ar','48000','-ac','1','-f','f32le','-']),dtype='<f4')
 errors=[]
 for t in [1,6,13,22,30,37]:
  center=t*48000;low=center-2400;part=mixed[center:center+48000].astype(float)/32768
  match=low+int(np.argmax(correlate(actual[low:center+50400],part,mode='valid',method='fft')));errors.append(abs(match-center)/48000)
 assert max(errors)<.005 and np.max(np.abs(actual))<.999
 assert all(meta['config'][k]==oldmeta['config'][k] for k in meta['config'] if k!='level_db_below_voice')
 fact('approved-music-level',1.8<=increase<=2.2 and meta['config']['level_db_below_voice']==18)
 pref=json.loads((Path.home()/'.codex/skills/local-feature-videos/music-preference.json').read_text())
 fact('selected-music-b',pref['selected_recurring_style']=='light-keys' and pref['level_db_below_voice']==18 and pref['decision_ref']=='source-0e756fa8e2b29cd970ff83cf')
 with av.open(str(FINAL/'rd-documentos-completo.mp4')) as c:
  v=c.streams.video[0];a=c.streams.audio[0];duration=float(v.duration*v.time_base)
  assert abs(duration-float(a.duration*a.time_base))<.05 and abs(duration-oldmeta['duration'])<.04
  count=sum(1 for f in c.decode(video=0))
 assert count==1199 and q.first_frame_ok(frame_at(FINAL/'rd-documentos-completo.mp4',0))
 image_metrics=[]
 for e in plan['actions']:
  t=e['pulse_at'];original=np.array(frame_at(SOURCE/'rd-documentos-completo.mp4',t)).astype(float);after=np.array(frame_at(FINAL/'rd-documentos-completo.mp4',t)).astype(float)
  x,y,w,h=e['rect'];region=abs(after-original)[y:y+h+1,x:x+w+1]
  if e['kind']!='status':assert (region.max(axis=2)>35).sum()>250
  # The narrated captions remain outside the annotation region.
  assert abs(after-original)[1090:1200].mean()<2.5
  image_metrics.append({'id':e['id'],'timestamp':t,'changed_pixels':int((region.max(axis=2)>35).sum())})
 visual=json.loads((OUT/'visual-review.json').read_text())
 assert visual['sheet_sha256']==b.sha(OUT/'actions-after.jpg') and visual['observer']=='Codex visual inspection'
 fact('visible-actions',len(image_metrics)==5 and visual['inspected'] and {e['cue_id'] for e in plan['actions']} >= {'open','upload','save'})
 rejected=0
 for mutate in [lambda p:p.update(source_sha256='wrong'),lambda p:p['actions'][0].update(start=float('nan')),lambda p:p['actions'][0].update(rect=[0,0,40,40]),lambda p:p['actions'][1].update(start=4.7),lambda p:p['actions'][0].update(cue_id='fake')]:
  bad=copy.deepcopy(plan);mutate(bad)
  try:actions.validate(bad,SOURCE)
  except (ValueError,KeyError):rejected+=1
 assert rejected==5
 with tempfile.TemporaryDirectory(prefix='actions-replay-') as temp:
  temp=Path(temp)
  subprocess.run([sys.executable,str(ROOT/'scripts/local_video/actions.py'),'--source',str(SOURCE),'--plan',str(OUT/'actions-plan.json'),'--output',str(temp/'dry')],capture_output=True,check=True,timeout=120)
  subprocess.run([sys.executable,str(ROOT/'scripts/local_video/music.py'),'--source',str(temp/'dry'),'--plan',str(OUT/'music-plan.json'),'--output',str(temp/'final')],capture_output=True,check=True,timeout=60)
  assert b.sha(temp/'final/rd-documentos-completo.mp4')==b.sha(FINAL/'rd-documentos-completo.mp4')
  assert b.sha(temp/'final/mezcla.wav')==b.sha(FINAL/'mezcla.wav')
 frozen=json.loads((OUT/'unchanged-backend.json').read_text());assert all(b.sha(ROOT/p)==h for p,h in frozen.items())
 installed=Path.home()/'.codex/skills/local-feature-videos'
 for name in ['actions.md','default-music-plan.json','music.md','music-preference.json']:assert b.sha(installed/name)==b.sha(ROOT/'scripts/local_video/skill/local-feature-videos'/name)
 subprocess.run([str(ROOT/'.venv/bin/python'),'-m','pytest','tests/test_feature_video_pipeline.py::test_approved_video_defaults','-q'],cwd=ROOT,capture_output=True,check=True)
 fact('regenerated-video-b',meta['tts_calls']==meta['model_api_calls']==0 and count==1199)
 fact('local-action-recipe',rejected==5 and all(b.sha(ROOT/p)==h for p,h in frozen.items()))
 print(json.dumps({'duration_seconds':duration,'music_before_lufs':previous,'music_after_lufs':lufs,'increase_db':increase,'decoded_peak':float(np.max(np.abs(actual))),'maximum_sync_error_seconds':max(errors),'frames':count,'actions':image_metrics,'replay_identical':True,'target':str(FINAL.relative_to(ROOT))}))
try:main()
finally:print('NIENFOS_OBSERVATIONS_V1 '+json.dumps({'observations':facts}))
