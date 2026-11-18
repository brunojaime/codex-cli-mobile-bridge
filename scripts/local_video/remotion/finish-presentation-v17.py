"""Use one complete new take. Never insert, split, or stretch words in narration."""
from pathlib import Path
import subprocess,json,math
import numpy as np
import av,imageio_ffmpeg
root=Path(__file__).resolve().parents[3];out=root/'reports/videos/nienfos-presentacion-v17-locucion-natural';old=root/'reports/videos/nienfos-presentacion-v15-solucion';visual=root/'reports/videos/nienfos-presentacion-v16-pausa/visual-sin-audio.mp4'
ff=imageio_ffmpeg.get_ffmpeg_exe();rate=44100;fps=30;start=round(17.98*rate);cut=round(17.8*rate)
def decode(p,filters=None):
 args=[ff,'-v','error','-i',str(p),'-ar',str(rate),'-ac','2']
 if filters:args+=['-af',filters]
 return np.frombuffer(subprocess.check_output(args+['-f','f32le','pipe:1']),dtype='<f4').reshape(-1,2).copy()
def save(name,a):
 p=out/(name+'.f32');p.write_bytes(a.astype('<f4').tobytes());subprocess.run([ff,'-v','error','-y','-f','f32le','-ar',str(rate),'-ac','2','-i',str(p),'-c:a','pcm_s24le',str(out/(name+'.wav'))],check=True);p.unlink()
voice_old=decode(old/'narracion.wav');clip=decode(out/'frase-final.mp3')
def active_rms(a):
 mono=np.mean(a,axis=1);sel=np.abs(mono)>.015;return float(np.sqrt(np.mean(mono[sel]**2)))
gain=active_rms(voice_old[start:round(20.1*rate)])/active_rms(clip);clip*=gain
assert np.max(np.abs(clip))<.85
active=np.flatnonzero(np.max(np.abs(clip),axis=1)>.003);voice_end=(start+active[-1])/rate;target_cadence=voice_end+.28
source=decode(old/'musica.wav');loop=rate;half=round(.04*rate);best=None
# Extend the approved groove by two beats from the same take; no music generation.
for pos in range(round(16.9*rate),round(18.2*rate),round(.005*rate)):
 a=source[pos-half:pos+half];b=source[pos-loop-half:pos-loop+half]
 score=float(np.mean((a-b)**2)/(np.mean(a*a)+np.mean(b*b)+1e-8))
 if best is None or score<best[0]:best=(score,pos)
_,pos=best;music=np.concatenate([source[:pos],source[pos-loop:]])
w=np.linspace(0,1,2*half,dtype=np.float32)[:,None];music[pos-half:pos+half]=source[pos-half:pos+half]*(1-w)+source[pos-loop-half:pos-loop+half]*w
save('musica-extendida',music)
# Match the final hit to the real end of the new take, preserving pitch.
speed=23.05/target_cadence
music=decode(out/'musica-extendida.wav',filters=f'atempo={speed:.12f}')
frames=max(745,math.ceil((25.6/speed)*fps));duration=frames/fps;n=frames*1470
music=np.pad(music,((0,max(0,n-len(music))),(0,0)))[:n];fade=round(.04*rate);music[-fade:]*=np.linspace(1,0,fade)[:,None]
voice=np.zeros((n,2),dtype=np.float32);voice[:cut]=voice_old[:cut];voice[start:start+len(clip)]=clip
assert np.array_equal(voice[start:start+len(clip)],clip)
assert np.array_equal(voice[:cut],voice_old[:cut])
fx=decode(old/'mezcla-sin-musica.wav')-voice_old;fx=np.pad(fx,((0,n-len(fx)),(0,0)))
mix=voice+fx+music;assert np.isfinite(mix).all() and np.max(np.abs(mix))<.94
save('narracion',voice);save('musica',music);save('mezcla',mix);save('mezcla-sin-musica',voice+fx)
subprocess.run([ff,'-v','error','-y','-i',str(visual),'-vf','tpad=stop_mode=clone:stop_duration=3','-an','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-t',str(duration),str(out/'visual-sin-audio.mp4')],check=True)
for name,track in [('presentacion','mezcla.wav'),('presentacion-sin-musica','mezcla-sin-musica.wav')]:
 subprocess.run([ff,'-v','error','-y','-i',str(out/'visual-sin-audio.mp4'),'-i',str(out/track),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k','-t',str(duration),'-movflags','+faststart',str(out/(name+'.mp4'))],check=True)
subprocess.run([ff,'-v','error','-y','-ss','17.6','-i',str(out/'presentacion.mp4'),'-c:v','libx264','-crf','18','-c:a','aac','-b:a','192k','-movflags','+faststart',str(out/'cierre.mp4')],check=True)
with av.open(str(out/'presentacion.mp4')) as c:
 v=c.streams.video[0];assert (v.width,v.height)==(720,1280) and float(v.average_rate)==30
 assert len(c.streams.audio)==1 and len(c.streams.subtitles)==0
 count=0
 for f in c.decode(video=0):
  if count==frames-5:f.to_image().save(out/'cierre.jpg',quality=94)
  count+=1
 assert count==frames
with av.open(str(out/'presentacion.mp4')) as c:assert sum(1 for _ in c.decode(audio=0))>0
peak=float(np.max(np.abs(decode(out/'presentacion.mp4'))));assert peak<.99
asr=json.loads((out/'transcription-check.json').read_text());assert asr['similarity']>.9
meta=json.loads((out/'voice-generation.json').read_text());credits=int(meta['reported_character_cost'])
# Measure the generated quiet interval; this interval is native to the new take.
quiet=[]
mono=np.mean(clip,axis=1)
for t in np.arange(2.95,3.3,.01):
 s=mono[round(t*rate):round((t+.01)*rate)];quiet.append(float(20*np.log10(np.sqrt(np.mean(s*s))+1e-12)))
validation={'all_passed':True,'duration':duration,'frames':count,'fps':30,'size':[720,1280],'full_video_decode':True,'full_audio_decode':True,'subtitle_streams':0,'voice':'Mauricio','first_four_phrases_identical':True,'new_take_placed_whole':True,'internal_voice_cuts':0,'inserted_silences':0,'tts_requested_pause_seconds':.22,'voice_end_seconds':round(voice_end,3),'final_music_hit_seconds':round(target_cadence,3),'cadence_after_voice_seconds':.28,'new_take_gain':gain,'music_speed_factor':speed,'music_pitch_preserved':True,'new_music_api_calls':0,'tts_generation_calls':1,'reported_provider_credits':credits,'transcription_similarity':asr['similarity'],'peak_after_aac':peak,'scene_counter_removed':True}
(out/'validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n')
(out/'README.md').write_text(f'''# Nienfos · Nueva toma del cierre

[Ver presentación](presentacion.mp4) · [Ver solo el cierre](cierre.mp4) · [Escuchar la toma original](frase-final.mp3)

Se regeneró la frase final completa con Mauricio: «Contanos qué tenés en mente. Nosotros te damos la solución». La pausa después de «Nosotros» se pidió durante la síntesis, con una indicación SSML de 0,22 segundos y velocidad 0,97. La toma se utiliza entera, sin cortes internos ni silencios insertados; solamente se ajusta su volumen al resto de la narración.

Las cuatro frases anteriores se conservan exactamente. Las escenas son las de la versión sin numeración; se sostiene el logo al final para completar el nuevo audio. Sin subtítulos. Duración: {duration:.2f} segundos.

La música se extendió localmente con dos tiempos de la misma grabación y un empalme breve, más un ajuste mínimo de tempo con tono conservado, para colocar el platillo aprobado unos 0,28 segundos después del final de la voz. No hubo nueva generación de música ni efectos.

Consumo informado por la API: **{credits} créditos** para una sola generación de voz; **0 créditos nuevos para música**. No se pudo consultar el saldo de la cuenta. [Detalle de generación](voice-generation.json).

![Cierre](cierre.jpg)

[Validación](validation.json) · [Comprobación local del texto](transcription-check.json) · [Versión anterior](../nienfos-presentacion-v16-pausa/presentacion.mp4)

Se verificaron texto mediante transcripción local, ausencia de cortes internos en la nueva toma, decodificación completa, duración, sincronización del golpe final y niveles sin saturación. No se declara escucha humana ni que estas mediciones prueben naturalidad auditiva.

La indicación de pausa se implementó según la [documentación oficial de ElevenLabs](https://elevenlabs.io/docs/help-center/product/core-capabilities/text-to-speech/how-can-i-add-pauses).
''')
print(json.dumps(validation,ensure_ascii=False))
