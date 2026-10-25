"""Verify the extra 1 dB music adjustment without changing approved video or voice."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys,tempfile
import av,numpy as np
from scipy.signal import correlate
import bookends as b,music
ROOT=b.ROOT;OUT=ROOT/'reports/rd-video-musica-ajuste-20260929';FINAL=OUT/'final';OLD=ROOT/'reports/rd-video-acciones-20260929/final';SOURCE=OLD.parent/'sin-musica'
facts={}
def video(path):
 h=hashlib.sha256();times=[]
 with av.open(str(path)) as c:
  for p in c.demux(video=0):
   if p.size:h.update(bytes(p));times.append((float(p.pts*p.time_base),float(p.duration*p.time_base)))
 return h.hexdigest(),times
try:
 parser=argparse.ArgumentParser();parser.add_argument('--focused',action='store_true');args=parser.parse_args()
 if not args.focused:
  r=subprocess.run([sys.executable,str(ROOT/'scripts/local_video/check_actions.py')],capture_output=True,text=True,check=True,timeout=540)
  facts.update(json.loads(next(x.split(' ',1)[1] for x in r.stdout.splitlines() if x.startswith('NIENFOS_OBSERVATIONS_V1 ')))['observations'])
 assert video(FINAL/'rd-documentos-completo.mp4')==video(OLD/'rd-documentos-completo.mp4')
 for file in ['narracion.wav','subtitulos.srt']:assert b.sha(FINAL/file)==b.sha(OLD/file)
 dry=b.read_pcm(FINAL/'narracion.wav');bed=b.read_pcm(FINAL/'musica.wav');mixed=b.read_pcm(FINAL/'mezcla.wav')
 assert np.array_equal(mixed.astype(np.int32)-bed.astype(np.int32),dry.astype(np.int32))
 previous=music.integrated_lufs(b.read_pcm(OLD/'musica.wav'));current=music.integrated_lufs(bed)
 assert .8<=current-previous<=1.2
 meta=json.loads((FINAL/'music.json').read_text());assert meta['music_rms_db_relative_to_active_voice']<-20
 actual=np.frombuffer(subprocess.check_output([b.FF,'-v','error','-i',str(FINAL/'rd-documentos-completo.mp4'),'-vn','-ar','48000','-ac','1','-f','f32le','-']),dtype='<f4')
 assert np.max(np.abs(actual))<.97
 errors=[]
 for t in [1,6,13,22,30,37]:
  center=t*48000;low=center-2400;part=mixed[center:center+48000].astype(float)/32768
  match=low+int(np.argmax(correlate(actual[low:center+50400],part,mode='valid',method='fft')));errors.append(abs(match-center)/48000)
 assert max(errors)<.005
 with av.open(str(FINAL/'rd-documentos-completo.mp4')) as c:
  v=c.streams.video[0];a=c.streams.audio[0];duration=float(v.duration*v.time_base)
  assert abs(duration-float(a.duration*a.time_base))<.05 and abs(duration-39.96666666666667)<.001
  assert sum(1 for f in c.decode(video=0))==1199
 with tempfile.TemporaryDirectory(prefix='rd-music-plus-') as temp:
  subprocess.run([sys.executable,str(ROOT/'scripts/local_video/music.py'),'--source',str(SOURCE),'--plan',str(OUT/'music-plan.json'),'--output',temp],check=True,capture_output=True,timeout=60)
  assert b.sha(Path(temp)/'rd-documentos-completo.mp4')==b.sha(FINAL/'rd-documentos-completo.mp4')
  assert b.sha(Path(temp)/'mezcla.wav')==b.sha(FINAL/'mezcla.wav')
 facts['approved-music-level']=.8<=current-previous<=1.2 and meta['music_rms_db_relative_to_active_voice']<-20
 facts['regenerated-video-b']=meta['tts_calls']==meta['model_api_calls']==0 and max(errors)<.005
 print(json.dumps({'duration_seconds':duration,'previous_music_lufs':previous,'music_lufs':current,'increase_db':current-previous,'music_db_relative_to_active_voice':meta['music_rms_db_relative_to_active_voice'],'decoded_peak':float(np.max(np.abs(actual))),'max_sync_error_seconds':max(errors),'video_packets_and_timestamps_identical':True,'voice_pcm_identical':True,'repeat_identical':True,'target':str(FINAL.relative_to(ROOT))}))
finally:print('NIENFOS_OBSERVATIONS_V1 '+json.dumps({'observations':facts}))
