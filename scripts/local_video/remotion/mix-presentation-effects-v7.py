"""Mix semantic sound cues against exact Remotion frame events, preserving narration."""
from pathlib import Path
import json,hashlib,subprocess,shutil
import numpy as np
import av,imageio_ffmpeg
root=Path(__file__).resolve().parents[3]
source=root/'reports/videos/nienfos-presentacion-v5-voces'
out=root/'reports/videos/nienfos-presentacion-v7-paleta-sonora';out.mkdir(exist_ok=True,parents=True)
ffmpeg=imageio_ffmpeg.get_ffmpeg_exe();rate=44100
plan=json.loads((source/'timing.json').read_text());generation=json.loads((out/'effects-generation.json').read_text())
def decode(path,channels=1):
 filters=['-af','highpass=f=70,lowpass=f=6500'] if path.parent.name=='efectos' else []
 raw=subprocess.check_output([ffmpeg,'-v','error','-i',str(path),'-ar',str(rate),'-ac',str(channels),*filters,'-f','f32le','pipe:1'])
 return np.frombuffer(raw,dtype='<f4').copy()
voice=decode(source/'mauricio/narracion.wav')
size=round(plan['duration']*rate);voice=np.pad(voice,(0,max(0,size-len(voice))))[:size]
# Keep narration at its approved gain, centered in stereo.
original=np.repeat(voice[:,None],2,axis=1);bed=np.zeros_like(original)
assets={};asset_metrics={}
for item in generation:
 name=item['name'];a=decode(out/'efectos'/f'{name}.mp3')
 block=220;pad=np.pad(a,(0,(-len(a))%block));rms=np.sqrt(np.mean(pad.reshape(-1,block)**2,axis=1))
 active=np.flatnonzero(rms>max(float(rms.max())*.035,.00008));assert active.size,name
 start=max(0,int(active[0])*block-int(.012*rate));end=min(len(a),int(active[-1]+1)*block+int(.05*rate));a=a[start:end]
 # Preserve native sample rate and pitch. Fade edges, never resample to a tiny click.
 fade=min(round(.018*rate),len(a)//3);a[:fade]*=np.linspace(0,1,fade);a[-fade:]*=np.linspace(1,0,fade)
 a/=max(float(np.sqrt(np.mean(a*a))),1e-8);assets[name]=a
 spectrum=np.abs(np.fft.rfft(a*np.hanning(len(a))))**2
 freqs=np.fft.rfftfreq(len(a),1/rate)
 asset_metrics[name]={'native_duration_seconds':round(len(a)/rate,4),'pitch_changed':False,'spectral_centroid_hz':round(float(np.sum(freqs*spectrum)/max(np.sum(spectrum),1e-9)),1)}

events=[]
def add(frame,effect,reason,pan=0,rms_db=-27):
 events.append({'frame':frame,'seconds':round(frame/30,4),'effect':effect,'reason':reason,'pan':pan,'target_rms_dbfs':rms_db})
add(4,'proyecto_revela','La portada entra en perspectiva y revela el sitio.',rms_db=-28)
for i,start in enumerate(plan['starts'][1:],1):
 add(start,'transicion_aire',f'Escena {i+1}: barrido horizontal de la composición.',pan=.15 if i%2 else -.15,rms_db=-29)
start=plan['starts'][1]
add(start+17,'papel_desliza','La primera tarjeta reúne la necesidad del cliente.',pan=-.15,rms_db=-27)
add(start+34,'linea_conecta','El conector lleva de la necesidad al análisis.',rms_db=-30)
add(start+56,'tarjeta_apoya','Se acomoda la tarjeta de escucha y análisis.',rms_db=-27)
add(start+94,'conexion_encaja','La marca de confirmación cierra el alcance acordado.',rms_db=-27)
start=plan['starts'][2]
add(start+16,'trazo_diseno','Se presenta la propuesta de diseño.',rms_db=-28)
add(start+46,'revision_pagina','La tarjeta de participación representa probar y revisar.',pan=.1,rms_db=-27)
add(start+94,'tarjeta_apoya','El resultado incorpora la devolución del cliente.',rms_db=-27)
start=plan['starts'][3]
add(start+30,'datos_circulan','La información empieza a circular por el primer conector.',pan=-.1,rms_db=-28)
add(start+56,'conexion_encaja','La tarjeta de integración conecta la información.',rms_db=-27)
add(start+65,'linea_conecta','El segundo conector lleva de integrar a simplificar.',rms_db=-30)
add(start+94,'tarjeta_apoya','La confirmación destaca menos tareas repetidas.',rms_db=-27)
add(plan['starts'][4]+25,'proyecto_revela','Se revela Chrem a la izquierda.',pan=-.5,rms_db=-28)
add(plan['starts'][4]+33,'proyecto_revela','Se revela RD a la derecha.',pan=.5,rms_db=-29)
add(plan['starts'][5]+9,'cierre_marca','El logo entra y se asienta en el cierre.',rms_db=-28)
events.sort(key=lambda e:e['frame'])
# Smooth narration activity envelope; attenuate effects by up to 3 dB while speech is active.
block=441;pad=np.pad(voice,(0,(-len(voice))%block));vrms=np.sqrt(np.mean(pad.reshape(-1,block)**2,axis=1))
activity=np.clip((vrms-.01)/.035,0,1)
smooth=np.convolve(activity,np.ones(9)/9,mode='same')
duck=np.interp(np.arange(size),np.arange(len(smooth))*block,10**(-3*smooth/20))
for event in events:
 a=assets[event['effect']].copy()*10**(event['target_rms_dbfs']/20)
 offset=round(event['frame']/30*rate);n=min(len(a),size-offset);assert offset>=0 and n>0
 a=a[:n]*duck[offset:offset+n]
 # Keep isolated transients restrained while retaining natural texture.
 if np.max(np.abs(a))>.13:a*=.13/float(np.max(np.abs(a)))
 vlocal=voice[offset:offset+n];voice_rms=float(np.sqrt(np.mean(vlocal*vlocal)))
 ar=float(np.sqrt(np.mean(a*a)))
 # At events occurring over speech keep the effect at least 13 dB below the speech RMS.
 if voice_rms>.015 and ar>voice_rms*.22:a*=voice_rms*.22/ar
 pan=event['pan'];gains=np.array([1-max(0,pan)*.45,1+min(0,pan)*.45],dtype=np.float32)
 bed[offset:offset+n]+=a[:,None]*gains
 event.update(duration_seconds=round(n/rate,4),sample_count=n,measured_rms_dbfs=round(20*np.log10(max(float(np.sqrt(np.mean(a*a))),1e-10)),2),speech_rms_dbfs=round(20*np.log10(max(voice_rms,1e-10)),2))
# Voice gain stays unchanged. Reduce only the effects bed if extra headroom is needed.
fx_gain=1.
while np.max(np.abs(original+bed*fx_gain))>.94:
 fx_gain*=.9
 assert fx_gain>.05,'Unexpected headroom issue'
bed*=fx_gain;mixed=original+bed
assert np.isfinite(mixed).all() and np.max(np.abs(mixed))<.95

def save_wav(a,path):
 raw=path.with_suffix('.f32');raw.write_bytes(a.astype('<f4').tobytes())
 subprocess.run([ffmpeg,'-v','error','-y','-f','f32le','-ar',str(rate),'-ac','2','-i',str(raw),'-c:a','pcm_s24le',str(path)],check=True);raw.unlink()
save_wav(mixed,out/'mezcla.wav');save_wav(bed,out/'solo-efectos.wav')
video=out/'presentacion.mp4'
subprocess.run([ffmpeg,'-v','error','-y','-i',str(source/'mauricio/presentacion.mp4'),'-i',str(out/'mezcla.wav'),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k','-movflags','+faststart','-t',str(plan['duration']),str(video)],check=True)
# Check unchanged H264 packets and completely decode the delivered audio and video.
def packet_hash(path):
 h=hashlib.sha256()
 with av.open(str(path)) as c:
  for packet in c.demux(video=0):h.update(bytes(packet))
 return h.hexdigest()
assert packet_hash(video)==packet_hash(source/'mauricio/presentacion.mp4')
with av.open(str(video)) as c:
 assert len(c.streams.video)==1 and len(c.streams.audio)==1 and len(c.streams.subtitles)==0
 stream=c.streams.video[0];assert (stream.width,stream.height)==(720,1280)
 duration=float(stream.duration*stream.time_base);assert abs(duration-24.3)<.03
 count=sum(1 for _ in c.decode(video=0));assert count==729
with av.open(str(video)) as c:assert sum(1 for _ in c.decode(audio=0))>0
final=decode(video,channels=2);peak=float(np.max(np.abs(final)));assert peak<.99
mask=np.zeros(size,dtype=bool)
for e in events:
 offset=round(e['frame']/30*rate);n=e['sample_count'];mask[offset:offset+n]=True
assert np.max(np.abs((mixed-original)[~mask]))<1e-6
cost=sum(int(x.get('reported_character_cost') or 0) for x in generation)
editorial={'voice':'Mauricio','user_voice_name_interpretation':'Mariano interpreted as Mauricio, the sole male voice from the three delivered options.','fps':30,'duration':24.3,'source_video_sha256':hashlib.sha256((source/'mauricio/presentacion.mp4').read_bytes()).hexdigest(),'narration_sha256':hashlib.sha256((source/'mauricio/narracion.wav').read_bytes()).hexdigest(),'music':False,'subtitles':False,'effects_gain':fx_gain,'ducking_db':3,'asset_metrics':asset_metrics,'preserve_effect_pitch':True,'effect_eq':'70 Hz high-pass, 6500 Hz low-pass; applied only to effects','events':events}
(out/'sound-plan.json').write_text(json.dumps(editorial,ensure_ascii=False,indent=2)+'\n')
validation={'all_passed':True,'frames':count,'duration':duration,'size':[720,1280],'fps':30,'audio_streams':1,'subtitle_streams':0,'full_audio_decode':True,'full_video_decode':True,'video_packets_identical_to_approved_version':True,'voice_gain_unchanged':True,'effects_only_inside_planned_events':True,'event_count':len(events),'distinct_effects_used':len(set(e['effect'] for e in events)),'native_pitch_preserved':True,'peak_after_aac':round(peak,5),'reported_effect_generation_cost':cost,'new_voice_generation_calls':0}
(out/'validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n')
shutil.copy2(source/'portada.jpg',out/'portada.jpg')
shutil.copy2(source/'escenas.jpg',out/'escenas.jpg')
# A separate native-pitch palette reel makes the generated families easy to compare.
reel=[]
for name,a in assets.items():
 x=a*.045;x*=min(1,.20/max(float(np.max(np.abs(x))),1e-9))
 reel.extend([np.repeat(x[:,None],2,axis=1),np.zeros((int(.30*rate),2),dtype=np.float32)])
save_wav(np.concatenate(reel),out/'paleta-sonidos.wav')
lines=['# Nienfos · Diseño sonoro por contexto','', '[Ver presentación](presentacion.mp4)','', '24,3 segundos · voz de Mauricio · sin subtítulos ni música.','', 'Nueva paleta de diez efectos de ElevenLabs, con el timbre y la duración naturales. Se conserva la entrega anterior.','', '- Necesidades: deslizamiento de papel y apoyo de tarjetas.','- Diseño: trazo de lápiz y cambio de página para la revisión.','- Integración: pulsos de datos y encastre de conectores.','- Proyectos: apertura de paneles con desplazamiento estéreo.','- Cierre: un acento cálido de aire al asentarse la marca.','', 'Los sonidos aparecen ligados a acciones visibles. La cuadrícula decorativa no dispara sonidos. La voz conserva su ganancia y los efectos se atenúan suavemente mientras habla.','', '[Escuchar la paleta de diez sonidos](paleta-sonidos.wav) · [Escuchar el montaje de efectos sin voz](solo-efectos.wav) · [Versión anterior](../nienfos-presentacion-v6-sonidos/presentacion.mp4)','', '![Escenas](escenas.jpg)','', f'La API informó {cost} en character-cost para generar estos diez efectos. La voz se reutilizó.','', 'Verificación: decodificación de video y audio completos, niveles sin saturación, 729 fotogramas, cero pistas de subtítulos, imagen H264 idéntica a la versión elegida y efectos en sus intervalos previstos. Se verificaron mediciones y sincronización; no se declara una evaluación auditiva humana.','', '| Tiempo | Efecto | Relación con la imagen |','|---:|---|---|']
for e in events:lines.append(f"| {e['seconds']:.2f} s | {e['effect']} | {e['reason']} |")
lines+=['','[Plan por fotogramas](sound-plan.json) · [Validación](validation.json)']
(out/'README.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(validation,ensure_ascii=False))
