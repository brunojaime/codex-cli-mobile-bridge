"""Mix semantic sound cues against exact Remotion frame events, preserving narration."""
from pathlib import Path
import json,hashlib,subprocess,shutil
import numpy as np
import av,imageio_ffmpeg
root=Path(__file__).resolve().parents[3]
source=root/'reports/videos/nienfos-presentacion-v5-voces'
out=root/'reports/videos/nienfos-presentacion-v6-sonidos';out.mkdir(exist_ok=True,parents=True)
ffmpeg=imageio_ffmpeg.get_ffmpeg_exe();rate=44100
plan=json.loads((source/'timing.json').read_text());generation=json.loads((out/'effects-generation.json').read_text())
def decode(path,channels=1):
 raw=subprocess.check_output([ffmpeg,'-v','error','-i',str(path),'-ar',str(rate),'-ac',str(channels),'-f','f32le','pipe:1'])
 return np.frombuffer(raw,dtype='<f4').copy()
voice=decode(source/'mauricio/narracion.wav')
size=round(plan['duration']*rate);voice=np.pad(voice,(0,max(0,size-len(voice))))[:size]
# Keep narration at its approved gain, centered in stereo.
original=np.repeat(voice[:,None],2,axis=1);bed=np.zeros_like(original)
assets={}
lengths={'barrido':.36,'tarjeta':.16,'conexion':.28,'confirmacion':.40}
for name in lengths:
 a=decode(out/'efectos'/f'{name}.mp3')
 # Find the onset with a 5 ms RMS envelope, retaining a short natural attack.
 block=220;pad=np.pad(a,(0,(-len(a))%block));rms=np.sqrt(np.mean(pad.reshape(-1,block)**2,axis=1))
 active=np.flatnonzero(rms>max(float(rms.max())*.06,.0001));assert active.size,name
 start=max(0,int(active[0])*block-int(.008*rate));a=a[start:]
 # Compress only the effect's duration to the animation gesture; never change the voice.
 n=round(lengths[name]*rate);a=np.interp(np.linspace(0,len(a)-1,n),np.arange(len(a)),a).astype(np.float32)
 fade=min(round(.015*rate),len(a)//3);a[:fade]*=np.linspace(0,1,fade);a[-fade:]*=np.linspace(1,0,fade)
 a/=max(float(np.sqrt(np.mean(a*a))),1e-8);assets[name]=a

events=[]
def add(frame,effect,reason,pan=0,rms_db=-31):
 events.append({'frame':frame,'seconds':round(frame/30,4),'effect':effect,'reason':reason,'pan':pan,'target_rms_dbfs':rms_db})
add(4,'barrido','La portada entra y se acomoda en perspectiva.',rms_db=-31)
for i,start in enumerate(plan['starts'][1:],1):add(start,'barrido',f'Escena {i+1}: el barrido horizontal revela la nueva composición.',rms_db=-32)
for i in [1,2,3]:
 start=plan['starts'][i]
 add(start+25,'tarjeta',f'Flujo {i}: la primera tarjeta termina de acomodarse.',rms_db=-31)
 add(start+31,'conexion',f'Flujo {i}: se dibuja el primer conector.',rms_db=-34)
 add(start+57,'tarjeta',f'Flujo {i}: se acomoda la segunda tarjeta.',rms_db=-31)
 add(start+63,'conexion',f'Flujo {i}: se dibuja el segundo conector.',rms_db=-34)
 add(start+94,'confirmacion',f'Flujo {i}: aparece la marca de confirmación del resultado.',rms_db=-30)
add(plan['starts'][4]+25,'tarjeta','La captura de Chrem termina de entrar por la izquierda.',pan=-.4,rms_db=-31)
add(plan['starts'][4]+33,'tarjeta','La captura de RD termina de entrar por la derecha.',pan=.4,rms_db=-31)
add(plan['starts'][5]+27,'confirmacion','El logo del cierre termina de acomodarse.',rms_db=-32)
events.sort(key=lambda e:e['frame'])
# Smooth narration activity envelope; attenuate effects by up to 5 dB while speech is active.
block=441;pad=np.pad(voice,(0,(-len(voice))%block));vrms=np.sqrt(np.mean(pad.reshape(-1,block)**2,axis=1))
activity=np.clip((vrms-.01)/.035,0,1)
smooth=np.convolve(activity,np.ones(9)/9,mode='same')
duck=np.interp(np.arange(size),np.arange(len(smooth))*block,10**(-5*smooth/20))
for event in events:
 a=assets[event['effect']].copy()*10**(event['target_rms_dbfs']/20)
 offset=round(event['frame']/30*rate);n=min(len(a),size-offset);assert offset>=0 and n>0
 a=a[:n]*duck[offset:offset+n]
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
editorial={'voice':'Mauricio','user_voice_name_interpretation':'Mariano interpreted as Mauricio, the sole male voice from the three delivered options.','fps':30,'duration':24.3,'source_video_sha256':hashlib.sha256((source/'mauricio/presentacion.mp4').read_bytes()).hexdigest(),'narration_sha256':hashlib.sha256((source/'mauricio/narracion.wav').read_bytes()).hexdigest(),'music':False,'subtitles':False,'effects_gain':fx_gain,'ducking_db':5,'events':events}
(out/'sound-plan.json').write_text(json.dumps(editorial,ensure_ascii=False,indent=2)+'\n')
validation={'all_passed':True,'frames':count,'duration':duration,'size':[720,1280],'fps':30,'audio_streams':1,'subtitle_streams':0,'full_audio_decode':True,'full_video_decode':True,'video_packets_identical_to_approved_version':True,'voice_gain_unchanged':True,'effects_only_inside_planned_events':True,'event_count':len(events),'peak_after_aac':round(peak,5),'reported_effect_generation_cost':cost,'new_voice_generation_calls':0}
(out/'validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n')
shutil.copy2(source/'portada.jpg',out/'portada.jpg')
shutil.copy2(source/'escenas.jpg',out/'escenas.jpg')
lines=['# Nienfos · Mauricio con sonidos de movimiento','', '[Ver presentación](presentacion.mp4)','', '24,3 segundos · 720×1280 · 30 fps · sin subtítulos ni música. Se usa la voz de **Mauricio** de la entrega anterior; se interpretó “Mariano” como esa opción masculina.','', '- Barridos suaves al cambiar de escena.','- Toques breves cuando se acomodan las tarjetas.','- Pulsos discretos al dibujarse los conectores.','- Confirmaciones al aparecer las marcas de resultado y el logo final.','- Desplazamiento estéreo suave en las dos tarjetas de clientes.','', 'La narración conserva su nivel. Los efectos se atenúan durante la voz y no suenan por el movimiento decorativo de la cuadrícula.','', '[Escuchar solo los efectos](solo-efectos.wav) · [Comparar con la versión sin efectos](../nienfos-presentacion-v5-voces/mauricio/presentacion.mp4)','', '![Escenas](escenas.jpg)','', f'Se generaron cuatro sonidos reutilizables con ElevenLabs; consumo informado: {cost} en `character-cost`. No se volvió a sintetizar la voz.','', 'Verificación: decodificación completa de audio y video; 729 fotogramas; ausencia de pistas de subtítulos y de saturación digital; datos H264 idénticos a la versión aprobada; efectos únicamente en los intervalos previstos. Se comprobaron tiempos y niveles, sin afirmar una escucha humana.','', '| Tiempo | Efecto | Relación con la imagen |','|---:|---|---|']
for e in events:lines.append(f"| {e['seconds']:.2f} s | {e['effect']} | {e['reason']} |")
lines+=['','[Plan por fotogramas](sound-plan.json) · [Validación](validation.json)']
(out/'README.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(validation,ensure_ascii=False))
