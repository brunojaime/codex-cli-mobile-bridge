"""Compare two understated music presets at the previously approved loudness."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys,tempfile
import av,numpy as np
from scipy.signal import correlate
import bookends as b,music,guide_qc as q
ROOT=b.ROOT;OUT=ROOT/'reports/rd-musica-opciones-20260929';SOURCE=ROOT/'reports/rd-video-editorial-20260929';OLD=ROOT/'reports/rd-video-musica-20260929'
facts={};metrics={}
def fact(k,v):facts[k]=bool(v);assert v,k

def packets(p):
 with av.open(str(p)) as c:
  h=hashlib.sha256();times=[]
  for pkt in c.demux(video=0):
   if pkt.size:h.update(bytes(pkt));times.append((float(pkt.pts*pkt.time_base),float(pkt.duration*pkt.time_base)))
 return h.hexdigest(),times

def decode(p):
 r=subprocess.run([b.FF,'-v','error','-i',str(p),'-vn','-ar','48000','-ac','1','-f','f32le','-'],capture_output=True,check=True)
 return np.frombuffer(r.stdout,dtype='<f4')

def main():
 p=argparse.ArgumentParser();p.add_argument('--focused',action='store_true');args=p.parse_args()
 if not args.focused:
  r=subprocess.run([sys.executable,str(ROOT/'scripts/local_video/check_music.py')],capture_output=True,text=True,check=True,timeout=360)
  facts.update(json.loads(next(x.split(' ',1)[1] for x in r.stdout.splitlines() if x.startswith('NIENFOS_OBSERVATIONS_V1 ')))['observations'])
 oldcfg=json.loads((OLD/'music-plan.json').read_text());oldbed=b.read_pcm(OLD/'musica.wav');old_lufs=music.integrated_lufs(oldbed)
 original=packets(SOURCE/'rd-documentos-completo.mp4');dry=b.read_pcm(SOURCE/'narracion.wav');stems=[];all_ok=[];details=[]
 def envelope_variation(x):
  y=x[96000:-96000].astype(float);y=y[:len(y)//2400*2400].reshape(-1,2400);rms=np.sqrt(np.mean(y*y,axis=1));return float(np.std(rms)/np.mean(rms))
 old_variation=envelope_variation(oldbed)
 with tempfile.TemporaryDirectory(prefix='music-options-') as temp:
  for folder,mode in [('a-pulso','soft-pulse'),('b-teclas','light-keys')]:
   out=OUT/folder;meta=json.loads((out/'music.json').read_text());cfg=music.validate(json.loads((out/'music-plan.json').read_text()));assert cfg['mode']==mode
   assert all(cfg[k]==oldcfg[k] for k in cfg if k!='mode')
   bed=b.read_pcm(out/'musica.wav');mixed=b.read_pcm(out/'mezcla.wav');stems.append(bed)
   assert np.array_equal(mixed.astype(np.int32)-bed.astype(np.int32),dry.astype(np.int32))
   assert packets(out/'rd-documentos-completo.mp4')==original
   assert b.sha(out/'subtitulos.srt')==b.sha(SOURCE/'subtitulos.srt')
   with av.open(str(out/'rd-documentos-completo.mp4')) as c:
    v=c.streams.video[0];a=c.streams.audio[0];duration=float(v.duration*v.time_base)
    assert abs(duration-float(a.duration*a.time_base))<.05 and abs(duration-39.9666666667)<.001
    assert q.first_frame_ok(next(c.decode(video=0)).to_image())
   actual=decode(out/'rd-documentos-completo.mp4');assert np.max(np.abs(actual))<.999
   errors=[]
   for t in [1,6,13,22,30,37]:
    center=t*48000;assert np.sqrt(np.mean(dry[center:center+48000].astype(float)**2))/32768>.015
    part=mixed[center:center+48000].astype(float)/32768;low=center-2400
    match=low+int(np.argmax(correlate(actual[low:center+50400],part,mode='valid',method='fft')));errors.append(abs(match-center)/48000)
   lufs=music.integrated_lufs(bed);variation=envelope_variation(bed)
   assert variation>old_variation+.08,'No measurable articulation beyond the sustained pad'
   assert abs(lufs-old_lufs)<=1 and max(errors)<.005
   assert meta['tts_calls']==meta['model_api_calls']==0
   dest=Path(temp)/folder
   subprocess.run([sys.executable,str(ROOT/'scripts/local_video/music.py'),'--source',str(SOURCE),'--plan',str(out/'music-plan.json'),'--output',str(dest)],capture_output=True,check=True,timeout=60)
   assert b.sha(dest/'mezcla.wav')==b.sha(out/'mezcla.wav')
   assert out.joinpath('escucha-14s.mp3').exists()
   details.append({'preset':mode,'music_lufs':lufs,'difference_to_approved_lu':lufs-old_lufs,'envelope_variation':variation,'decoded_peak':float(np.max(np.abs(actual))),'maximum_audio_offset_seconds':max(errors),'repeat_pcm_identical':True})
   all_ok.append(True)
  invalid=Path(temp)/'bad.json';invalid.write_text(json.dumps({**oldcfg,'mode':'unknown'}))
  r=subprocess.run([sys.executable,str(ROOT/'scripts/local_video/music.py'),'--source',str(SOURCE),'--plan',str(invalid),'--output',str(Path(temp)/'bad')],capture_output=True)
  assert r.returncode!=0 and not (Path(temp)/'bad').exists()
 correlation=float(np.corrcoef(stems)[0,1]);assert abs(correlation)<.9
 fact('music-alternatives',len(all_ok)==2 and len(stems)==2 and abs(correlation)<.9 and OLD.joinpath('rd-documentos-completo.mp4').exists())
 fact('approved-music-level',all(abs(x['difference_to_approved_lu'])<=1 and x['decoded_peak']<.999 for x in details))
 base=ROOT/'scripts/local_video/skill/local-feature-videos';installed=Path.home()/'.codex/skills/local-feature-videos'
 for rel in ['SKILL.md','music.md','music-preference.json']:assert b.sha(base/rel)==b.sha(installed/rel)
 preference=json.loads((installed/'music-preference.json').read_text())
 subprocess.run([str(ROOT/'.venv/bin/python'),str(Path.home()/'.codex/skills/.system/skill-creator/scripts/quick_validate.py'),str(installed)],capture_output=True,check=True)
 fact('recurring-music-preference',preference['preferred_delivery']=='with-music' and (preference['selected_recurring_style'] is None or (preference['selected_recurring_style']=='light-keys' and preference['selection_status']=='user_selected' and preference['decision_ref'] in ('source-29b9f7e55017fc93e90f78f0','source-0e756fa8e2b29cd970ff83cf'))) and preference['level_db_below_voice']==(18 if preference['decision_ref']=='source-0e756fa8e2b29cd970ff83cf' else oldcfg['level_db_below_voice']) and len(all_ok)==2)
 metrics.update(approved_music_lufs=old_lufs,approved_envelope_variation=old_variation,presets=details,preset_correlation=correlation,criteria_passed=sum(facts.values()),target=str(OUT.relative_to(ROOT)))
 print(json.dumps(metrics))
try:main()
finally:print('NIENFOS_OBSERVATIONS_V1 '+json.dumps({'observations':facts}))
