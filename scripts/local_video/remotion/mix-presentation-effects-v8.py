"""Mix semantic sound cues against exact Remotion frame events, preserving narration."""
from pathlib import Path
import json,hashlib,subprocess,shutil
import numpy as np
import av,imageio_ffmpeg
root=Path(__file__).resolve().parents[3]
source=root/'reports/videos/nienfos-presentacion-v5-voces'
out=root/'reports/videos/nienfos-presentacion-v8-papel-clicks';out.mkdir(exist_ok=True,parents=True)
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
 # Reuse the exact approved click: remove surrounding quiet texture without changing pitch.
 if name=='conexion_encaja':
  peak_index=int(np.argmax(np.abs(a)));a=a[max(0,peak_index-int(.028*rate)):min(len(a),peak_index+int(.135*rate))]
 # Preserve native sample rate and pitch.

 fade=min(round((.003 if name=='conexion_encaja' else .018)*rate),len(a)//3);a[:fade]*=np.linspace(0,1,fade);a[-fade:]*=np.linspace(1,0,fade)
 a/=max(float(np.sqrt(np.mean(a*a))),1e-8);assets[name]=a
 spectrum=np.abs(np.fft.rfft(a*np.hanning(len(a))))**2
 freqs=np.fft.rfftfreq(len(a),1/rate)
 asset_metrics[name]={'native_duration_seconds':round(len(a)/rate,4),'pitch_changed':False,'spectral_centroid_hz':round(float(np.sum(freqs*spectrum)/max(np.sum(spectrum),1e-9)),1)}

events=[]
def add(frame,effect,reason,pan=0,rms_db=-27):
 events.append({'frame':frame,'seconds':round(frame/30,4),'effect':effect,'reason':reason,'pan':pan,'target_rms_dbfs':rms_db})
add(7,'papel_desliza','La portada se acomoda con roce de papel, sustituyendo la apertura grave.',rms_db=-31)
for i,start in enumerate(plan['starts'][1:],1):
 add(start,'revision_pagina' if i%2 else 'papel_desliza',f'Escena {i+1}: el cambio se acompaña con una hoja tenue.',pan=.12 if i%2 else -.12,rms_db=-35)
start=plan['starts'][1]
add(start+17,'papel_desliza','La primera tarjeta reúne la necesidad del cliente.',pan=-.15,rms_db=-28)
add(start+34,'linea_conecta','El conector une necesidad y análisis.',rms_db=-35)
add(start+56,'revision_pagina','Se organiza la tarjeta de análisis.',rms_db=-31)
add(start+94,'conexion_encaja','Clic aprobado al confirmar un alcance claro; más presente.',rms_db=-25)
start=plan['starts'][2]
add(start+16,'trazo_diseno','La propuesta se dibuja con una textura de lápiz tenue.',rms_db=-33)
add(start+46,'revision_pagina','Se revisa el diseño y se incorpora la devolución.',pan=.1,rms_db=-28)
add(start+94,'conexion_encaja','El mismo clic confirma el ajuste conjunto.',rms_db=-28)
start=plan['starts'][3]
add(start+30,'linea_conecta','La información recorre el conector, sin ráfagas digitales.',rms_db=-34)
add(start+56,'conexion_encaja','El clic acompaña la conexión de herramientas.',rms_db=-29)
add(start+94,'conexion_encaja','Clic breve al confirmar el resultado de la integración.',rms_db=-28)
add(plan['starts'][4]+20,'papel_desliza','La tarjeta de Chrem entra como una hoja.',pan=-.4,rms_db=-31)
add(plan['starts'][4]+33,'revision_pagina','La tarjeta de RD entra con un roce de página.',pan=.4,rms_db=-32)
add(plan['starts'][5]+27,'conexion_encaja','Un clic discreto al asentarse la marca.',rms_db=-30)
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
 limit=.19 if event['effect']=='conexion_encaja' else (.17 if event['effect'] in ['papel_desliza','revision_pagina'] else .11)
 if np.max(np.abs(a))>limit:a*=limit/float(np.max(np.abs(a)))
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
validation={'all_passed':True,'frames':count,'duration':duration,'size':[720,1280],'fps':30,'audio_streams':1,'subtitle_streams':0,'full_audio_decode':True,'full_video_decode':True,'video_packets_identical_to_approved_version':True,'voice_gain_unchanged':True,'effects_only_inside_planned_events':True,'event_count':len(events),'distinct_effects_used':len(set(e['effect'] for e in events)),'native_pitch_preserved':True,'metallic_low_effects_removed':True,'click_occurrences':sum(e['effect']=='conexion_encaja' for e in events),'peak_after_aac':round(peak,5),'reported_effect_generation_cost':cost,'new_voice_generation_calls':0}
(out/'validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n')
shutil.copy2(source/'portada.jpg',out/'portada.jpg')
shutil.copy2(source/'escenas.jpg',out/'escenas.jpg')
# A separate native-pitch palette reel makes the generated families easy to compare.
reel=[]
for name,a in assets.items():
 x=a*.045;x*=min(1,.20/max(float(np.max(np.abs(x))),1e-9))
 reel.extend([np.repeat(x[:,None],2,axis=1),np.zeros((int(.30*rate),2),dtype=np.float32)])
save_wav(np.concatenate(reel),out/'paleta-sonidos.wav')
# Compare the same reach-clear event against the previous mix.
previous=json.loads((root/'reports/videos/nienfos-presentacion-v7-paleta-sonora/sound-plan.json').read_text())
prior=next(e for e in previous['events'] if e['frame']==207)
now=next(e for e in events if e['frame']==207)
validation['reach_clear_click_rms_change_db']=round(now['measured_rms_dbfs']-prior['measured_rms_dbfs'],2)
(out/'validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n')
lines=['# Nienfos · Hojas y clics sutiles','', '[Ver presentación](presentacion.mp4)','', '24,3 segundos · voz de Mauricio · sin subtítulos ni música.','', '- Se reutiliza el clic que acompaña «un alcance claro», con más presencia y en cinco confirmaciones coherentes.','- Se destacan el deslizamiento de hojas y los cambios de página.','- Se retiran las aperturas graves de paneles, los barridos graves, las ráfagas de datos y el acento grave del cierre.','- Los cambios de escena quedan acompañados por hojas a menor volumen que las acciones.','', 'La imagen, la voz y sus tiempos se conservan. Los efectos previos siguen disponibles en la entrega anterior.','', '[Escuchar solo los efectos](solo-efectos.wav) · [Versión anterior](../nienfos-presentacion-v7-paleta-sonora/presentacion.mp4)','', '![Escenas](escenas.jpg)','', 'Se reutilizaron cinco sonidos de ElevenLabs ya generados; no hubo nuevas solicitudes ni consumo de créditos de la API. El clic conserva su tono y se recortó alrededor de su contacto para retirar la textura sobrante.','', 'Verificación: audio y video decodificados completos, niveles sin saturación, 729 fotogramas, cero pistas de subtítulos, imagen H264 idéntica, ganancia de voz conservada y efectos vinculados a los intervalos previstos. Se verificaron mediciones y sincronización, sin afirmar escucha humana.','', '| Tiempo | Efecto | Relación con la imagen |','|---:|---|---|']
for e in events:lines.append(f"| {e['seconds']:.2f} s | {e['effect']} | {e['reason']} |")
lines+=['','[Plan por fotogramas](sound-plan.json) · [Validación](validation.json)']
(out/'README.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(validation,ensure_ascii=False))
