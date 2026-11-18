from pathlib import Path
import subprocess,json,math
import numpy as np
import av,imageio_ffmpeg
root=Path(__file__).resolve().parents[3];out=root/'reports/videos/nienfos-presentacion-v15-solucion';old=root/'reports/videos/nienfos-presentacion-v12-cierre';song=root/'reports/videos/nienfos-presentacion-v10-groove'
ff=imageio_ffmpeg.get_ffmpeg_exe();rate=44100;duration=24.6;n=round(duration*rate);start=round(17.98*rate)
def decode(p,filters=None):
 args=[ff,'-v','error','-i',str(p),'-ar',str(rate),'-ac','2']
 if filters:args+=['-af',filters]
 raw=subprocess.check_output(args+['-f','f32le','pipe:1']);return np.frombuffer(raw,dtype='<f4').reshape(-1,2).copy()
def save(name,a):
 p=out/(name+'.f32');p.write_bytes(a.astype('<f4').tobytes());subprocess.run([ff,'-v','error','-y','-f','f32le','-ar',str(rate),'-ac','2','-i',str(p),'-c:a','pcm_s24le',str(out/(name+'.wav'))],check=True);p.unlink()
original_voice=decode(old/'narracion.wav');voice=np.zeros((n,2),dtype=np.float32);cut=round(17.8*rate);voice[:cut]=original_voice[:cut]
clip=decode(out/'frase-final.mp3');active=np.flatnonzero(np.max(np.abs(clip),axis=1)>.003);clip=clip[max(0,active[0]-round(.09*rate)):min(len(clip),active[-1]+round(.1*rate))]
reference=original_voice[start:round(20.1*rate)]
def active_rms(a):
 mono=np.mean(a,axis=1);sel=np.abs(mono)>.015;return float(np.sqrt(np.mean(mono[sel]**2)))
gain=active_rms(reference)/active_rms(clip);clip*=gain
assert np.max(np.abs(clip))<.85
voice[start:start+len(clip)]=clip
voice_end=(start+np.flatnonzero(np.max(np.abs(clip),axis=1)>.003)[-1])/rate
fx=decode(old/'solo-efectos.wav');fx=np.pad(fx,((0,n-len(fx)),(0,0)))
source=(decode(song/'mezcla.wav')-decode(song/'mezcla-sin-musica.wav'))[:round(22.6*rate)]
# Repeat one 2 s / 4-beat phrase from the same performance, keeping native pitch/tempo.
# Choose a splice with similar 80 ms stereo waveforms, avoiding the final cadence.
loop=2*rate;half=round(.04*rate);best=None
for pos in range(round(14.7*rate),round(17.5*rate),round(.005*rate)):
 a=source[pos-half:pos+half];b=source[pos-loop-half:pos-loop+half]
 # Relative error favors similar shape and level, rather than merely low energy.
 score=float(np.mean((a-b)**2)/(np.mean(a*a)+np.mean(b*b)+1e-8))
 if best is None or score<best[0]:best=(score,pos)
score,pos=best
music=np.concatenate([source[:pos],source[pos-loop:]])
assert len(music)==n
w=np.linspace(0,1,2*half,dtype=np.float32)[:,None]
music[pos-half:pos+half]=source[pos-half:pos+half]*(1-w)+source[pos-loop-half:pos-loop+half]*w
# Recover the same cadence and decay approved in v14, now delayed exactly two seconds.
t=np.arange(n)/rate;music*= (1+.20*np.clip((t-21.85)/.25,0,1))[:,None]
fade=round(.12*rate);music[-fade:]*=np.linspace(1,0,fade)[:,None]
mix=voice+fx+music;assert np.isfinite(mix).all() and np.max(np.abs(mix))<.94
save('narracion',voice);save('musica',music);save('mezcla-sin-musica',voice+fx);save('mezcla',mix)
for name,track in [('presentacion','mezcla.wav'),('presentacion-sin-musica','mezcla-sin-musica.wav')]:
 subprocess.run([ff,'-v','error','-y','-i',str(out/'visual-sin-audio.mp4'),'-i',str(out/track),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k','-t',str(duration),'-movflags','+faststart',str(out/(name+'.mp4'))],check=True)
subprocess.run([ff,'-v','error','-y','-ss','16.5','-i',str(out/'presentacion.mp4'),'-c:v','libx264','-crf','18','-c:a','aac','-b:a','192k','-movflags','+faststart',str(out/'cierre.mp4')],check=True)
with av.open(str(out/'presentacion.mp4')) as c:
 v=c.streams.video[0];assert (v.width,v.height)==(720,1280) and float(v.average_rate)==30
 assert len(c.streams.audio)==1 and len(c.streams.subtitles)==0
 frames=0
 for f in c.decode(video=0):
  if frames==685:f.to_image().save(out/'cierre.jpg',quality=94)
  frames+=1
 assert frames==738
with av.open(str(out/'presentacion.mp4')) as c:assert sum(1 for _ in c.decode(audio=0))>0
peak=float(np.max(np.abs(decode(out/'presentacion.mp4'))));assert peak<.99
assert np.array_equal(voice[:cut],original_voice[:cut])
# Guard unchanged visuals except the final label and extended final scene.
src=root/'scripts/local_video/remotion/src';a=(src/'PresentationV13.tsx').read_text();b=(src/'PresentationV15.tsx').read_text()
assert a[a.index('const Background:'):a.index('const Shot:')]==b[b.index('const Background:'):b.index('const Shot:')]
meta=json.loads((out/'voice-generation.json').read_text());credits=int(meta['reported_character_cost'])
validation={'all_passed':True,'duration':duration,'frames':frames,'fps':30,'size':[720,1280],'full_video_decode':True,'full_audio_decode':True,'subtitle_streams':0,'peak_after_aac':peak,'voice':'Mauricio','closing_text':meta['text'],'first_four_narration_scenes_identical':True,'new_voice_gain':gain,'closing_voice_end_seconds':round(voice_end,3),'cadence_attack_seconds':22.05,'cadence_after_voice_seconds':round(22.05-voice_end,3),'music_added_seconds':2,'music_splice_seconds':round(pos/rate,4),'music_splice_crossfade_seconds':.08,'music_pitch_and_speed_unchanged':True,'new_music_api_calls':0,'tts_generation_calls':1,'reported_provider_credits':credits,'visual_components_unchanged':True}
(out/'validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n')
(out/'README.md').write_text(f'''# Nienfos · Nosotros te damos la solución

[Ver presentación](presentacion.mp4) · [Ver solo el cierre](cierre.mp4)

24,6 segundos · 720×1280 · 30 fps · sin subtítulos.

La nueva locución final de Mauricio dice: «Contanos qué tenés en mente. Nosotros te damos la solución». Se reemplazó únicamente esa frase y se ajustó su nivel al de la voz anterior. Las cuatro frases anteriores se conservan exactamente.

La música se extendió dos segundos mediante la repetición de un compás de la misma grabación, con un empalme de 80 ms, sin cambios de tono ni velocidad. El golpe final aprobado se sitúa alrededor de 22,05 s: {22.05-voice_end:.2f} s después de la voz. Se deja resonar la cola musical sobre el cierre. No se generó otra canción ni otro efecto.

Las pantallas web y móvil, el tablero y las conexiones conservan sus componentes. El cierre dura más y su línea de apoyo ahora dice «Nosotros te damos la solución».

Consumo: **{credits} créditos**, informados por el encabezado `character-cost` de una sola generación TTS de 59 caracteres. **0 créditos adicionales para música**. La consulta de saldo no estuvo disponible; no se presenta una estimación del saldo total de la cuenta.

![Cierre](cierre.jpg)

[Sin música](presentacion-sin-musica.mp4) · [Validación](validation.json) · [Detalle de voz](voice-generation.json) · [Versión anterior](../nienfos-presentacion-v14-final-musical/presentacion.mp4)

Verificación instrumental de decodificación, duración, sincronización de voz y golpe final, preservación de la locución previa y niveles sin saturación. No se declara escucha humana. Integración TTS según la [documentación oficial](https://elevenlabs.io/docs/api-reference/text-to-speech/convert).
''')
print(json.dumps(validation,ensure_ascii=False))
