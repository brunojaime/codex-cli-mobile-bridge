"""Optional original procedural ambient bed; deterministic local mix, no model or network."""
from pathlib import Path
import argparse,json,math,shutil,time,wave,re,subprocess,tempfile
import numpy as np
import av
from bookends import read_pcm,write_pcm,command,sha,SR,FF

DEFAULT={'version':1,'mode':'soft-ambient','level_db_below_voice':20,'duck_db':5,'fade_in_seconds':1.2,'fade_out_seconds':1.8,'duck_attack_seconds':.18}

def validate(cfg):
 if set(cfg)!=set(DEFAULT) or cfg['version']!=1 or cfg['mode'] not in ('none','soft-ambient','soft-pulse','light-keys'):raise ValueError('Invalid music plan')
 for key,lo,hi in [('level_db_below_voice',18,40),('duck_db',0,12),('fade_in_seconds',.5,4),('fade_out_seconds',.5,4),('duck_attack_seconds',.05,.5)]:
  x=cfg[key]
  if isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or not lo<=x<=hi:raise ValueError('Invalid music parameter: '+key)
 return cfg

def smooth(t):return np.clip(t,0,1)**2*(3-2*np.clip(t,0,1))
def pad(n,sr):
 # Cmaj9 – Am9 – Fmaj9 – Cmaj9, slow crossfaded sine/soft-harmonic voicings.
 chords=[[48,55,59,62,64],[45,52,55,59,60],[53,57,60,64,67],[48,55,59,62,64]]
 t=np.arange(n)/sr;duration=n/sr;length=duration/4;mix=np.zeros(n);weight=np.zeros(n)
 for i,notes in enumerate(chords):
  start=i*length;end=(i+1)*length
  env=smooth((t-start+1.6)/1.6)*(1-smooth((t-end)/1.6))
  if i==0:env[t<start]=1
  value=np.zeros(n)
  for j,midi in enumerate(notes):
   freq=440*2**((midi-69)/12);phase=2*np.pi*freq*t+.012*np.sin(2*np.pi*(.08+j*.012)*t)
   value+=(np.sin(phase+j*.43)+.12*np.sin(2*phase+j*.2)+.035*np.sin(3*phase))/(1+j*.18)
  mix+=value*env;weight+=env
 mix/=np.maximum(weight,1);mix/=np.sqrt(np.mean(mix**2))
 return mix

def articulated(n,sr,style):
 # Original understated accompaniment; pitched attacks, no drum/noise track.
 bpm=92 if style=='soft-pulse' else 100;beat=60/bpm
 chords=[[48,55,60,64,67],[43,55,59,62,67],[45,57,60,64,69],[41,53,57,60,65]]
 out=np.zeros(n)
 def note(start,midi,duration,amp,decay):
  first=round(start*sr);count=min(round(duration*sr),n-first)
  if count<=0:return
  t=np.arange(count)/sr;f=440*2**((midi-69)/12)
  env=(1-np.exp(-t/.028))*np.exp(-t/decay)*smooth((duration-t)/.12)
  tone=np.sin(2*np.pi*f*t)+.22*np.sin(2*np.pi*2*f*t)*np.exp(-t/.22)+.055*np.sin(2*np.pi*3*f*t)*np.exp(-t/.12)
  out[first:first+count]+=amp*env*tone
 for k,start in enumerate(np.arange(0,n/sr,beat)):
  chord=chords[(k//8)%4]
  if style=='soft-pulse':
   note(start,chord[0],1.2,.55,.55)
   for midi in chord[2:]:note(start+beat*.5,midi,1.1,.20,.38)
  else:
   # Sparse electric-key pattern with alternate voicings; no lead melody.
   if k%2==0:
    for midi in chord[1:4]:note(start,midi,1.8,.28,.75)
   note(start+beat*.5,chord[[2,3,4,3][k%4]],1.2,.20,.48)
 out += pad(n,sr)*(.18 if style=='soft-pulse' else .12)
 out/=np.sqrt(np.mean(out*out))
 return out

def integrated_lufs(samples):
 with tempfile.TemporaryDirectory(prefix='music-level-') as temp:
  path=Path(temp)/'stem.wav';write_pcm(path,samples)
  r=subprocess.run([FF,'-v','info','-i',str(path),'-af','ebur128','-f','null','-'],capture_output=True,text=True,check=True)
  values=re.findall(r'I:\s*(-?[0-9.]+) LUFS',r.stderr)
  if not values:raise ValueError('Unable to measure music loudness')
  return float(values[-1])

def components(dry,cfg):
 x=dry.astype(float)/32768;n=len(x);t=np.arange(n)/SR
 blocks=np.sqrt(np.mean(x[:n//480*480].reshape(-1,480)**2,axis=1));active=blocks>10**(-38/20)
 if not active.any():raise ValueError('Narration has no measurable speech')
 voice_rms=float(np.sqrt(np.mean(blocks[active]**2)));start=int(np.flatnonzero(active)[0])*480/SR
 if cfg['mode']=='none':return np.zeros(n,dtype='<i2'),{'voice_active_rms':voice_rms,'first_speech_seconds':start}
 bed=pad(n,SR) if cfg['mode']=='soft-ambient' else articulated(n,SR,cfg['mode']);base_rms=voice_rms*10**(-cfg['level_db_below_voice']/20)
 # Attenuate just before first speech and hold to the end, including reading pauses.
 # No releases between phrases, so silence never triggers a distracting swell.
 duck_start=max(0,start-.12-cfg['duck_attack_seconds'])
 duck=1-(1-10**(-cfg['duck_db']/20))*smooth((t-duck_start)/cfg['duck_attack_seconds'])
 fade=smooth(t/cfg['fade_in_seconds'])*smooth(((n-1)/SR-t)/cfg['fade_out_seconds'])
 music=np.round(bed*base_rms*duck*fade*32768).astype('<i2')
 return music,{'voice_active_rms':voice_rms,'first_speech_seconds':start,'duck_start_seconds':duck_start,'duck_full_seconds':duck_start+cfg['duck_attack_seconds'],'duck_policy':'hold through narration and reading pauses until end','base_music_rms':base_rms}

def render(source,output,plan):
 started=time.perf_counter();source=Path(source).resolve();out=Path(output).resolve();cfg=validate(json.loads(Path(plan).read_text()))
 if source==out:raise ValueError('Preserve the source video; use a separate output directory')
 movie=source/'rd-documentos-completo.mp4';dry=read_pcm(source/'narracion.wav')
 with av.open(str(movie)) as c:duration=float(c.streams.video[0].duration*c.streams.video[0].time_base)
 if abs(duration-len(dry)/SR)>.001:raise ValueError('Voice and video durations differ')
 music,info=components(dry,cfg)
 if cfg['mode'] in ('soft-pulse','light-keys'):
  reference,_=components(dry,{**cfg,'mode':'soft-ambient'})
  target=integrated_lufs(reference);before=integrated_lufs(music);gain_db=target-before
  music=np.round(music.astype(float)*10**(gain_db/20)).astype('<i2')
  after=integrated_lufs(music)
  if abs(after-target)>1:raise ValueError('Music loudness does not match approved reference')
  info.update(reference_music_lufs=target,music_lufs=after,loudness_calibration_db=gain_db,tempo_bpm=92 if cfg['mode']=='soft-pulse' else 100)
 mixed=dry.astype(np.int32)+music.astype(np.int32)
 if np.max(np.abs(mixed))>=.97*32768:raise ValueError('Insufficient mix headroom; reduce music level')
 out.mkdir(parents=True,exist_ok=True)
 for name in ['narracion.wav','subtitulos.srt','portada.jpg','intro.png','outro.png']:
  if (source/name).exists():shutil.copyfile(source/name,out/name)
 write_pcm(out/'musica.wav',music);write_pcm(out/'mezcla.wav',mixed)
 if cfg['mode']=='none':shutil.copyfile(movie,out/'rd-documentos-completo.mp4')
 else:command(['-i',movie,'-i',out/'mezcla.wav','-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','128k','-movflags','+faststart',out/'rd-documentos-completo.mp4'])
 command(['-i',out/'mezcla.wav','-c:a','libmp3lame','-b:a','128k',out/'audio-con-musica.mp3'])
 meta=json.loads((source/'render.json').read_text());meta.update(video_sha256=sha(out/'rd-documentos-completo.mp4'),source_video_sha256=sha(movie),music_plan=cfg)
 (out/'render.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
 full_duck=max(0,round(info.get('duck_full_seconds',0)*SR));ratio=float(np.sqrt(np.mean(music[full_duck:].astype(float)**2)))/32768/info['voice_active_rms']
 info.update(config=cfg,duration=duration,seconds=time.perf_counter()-started,narration_sha256=sha(source/'narracion.wav'),source_video_sha256=sha(movie),music_sha256=sha(out/'musica.wav'),mixed_sha256=sha(out/'mezcla.wav'),mixed_peak=float(np.max(np.abs(mixed)))/32768,music_rms_db_relative_to_active_voice=20*math.log10(max(ratio,1e-12)),tts_calls=0,model_api_calls=0,provenance=cfg['mode']+'-v1: original procedural accompaniment defined in scripts/local_video/music.py; no recordings, external tracks, models or downloaded samples')
 (out/'music.json').write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n');print(json.dumps(info))
 return info
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--plan',type=Path,required=True);a=p.parse_args();render(a.source,a.output,a.plan)
