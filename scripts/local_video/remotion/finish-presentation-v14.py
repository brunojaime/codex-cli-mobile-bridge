"""Restore the approved song's original cadence. No synthesis/provider requests."""
from pathlib import Path
import json, subprocess, hashlib, shutil
import numpy as np
import av,imageio_ffmpeg
root=Path(__file__).resolve().parents[3];out=root/'reports/videos/nienfos-presentacion-v14-final-musical';out.mkdir(parents=True,exist_ok=True)
old=root/'reports/videos/nienfos-presentacion-v13-kanban';dry=root/'reports/videos/nienfos-presentacion-v12-cierre';song=root/'reports/videos/nienfos-presentacion-v10-groove'
ff=imageio_ffmpeg.get_ffmpeg_exe();rate=44100;duration=22.6;n=round(duration*rate)
def decode(p):
 b=subprocess.check_output([ff,'-v','error','-i',str(p),'-ar',str(rate),'-ac','2','-f','f32le','pipe:1']);return np.frombuffer(b,dtype='<f4').reshape(-1,2).copy()
def save(name,a):
 p=out/(name+'.f32');p.write_bytes(a.astype('<f4').tobytes());subprocess.run([ff,'-v','error','-y','-f','f32le','-ar',str(rate),'-ac','2','-i',str(p),'-c:a','pcm_s24le',str(out/(name+'.wav'))],check=True);p.unlink()
base=decode(dry/'mezcla-sin-musica.wav');base=np.pad(base,((0,n-len(base)),(0,0)))
# Difference of lossless approved mixes recovers the approved music/EQ/gain.
music=(decode(song/'mezcla.wav')-decode(song/'mezcla-sin-musica.wav'))[:n]
# Original groove continues under the CTA, then a gentle 1.58 dB lift exposes the cadence.
t=np.arange(n)/rate;lift=1+.20*np.clip((t-19.85)/.25,0,1);music*=lift[:,None]
# Keep almost all the natural decay; remove only the very last 120 ms at very low level.
fade=round(.12*rate);music[-fade:]*=np.linspace(1,0,fade)[:,None]
mix=base+music;assert np.isfinite(mix).all() and np.max(np.abs(mix))<.94
save('musica',music);save('mezcla',mix)
subprocess.run([ff,'-v','error','-y','-i',str(old/'visual-sin-audio.mp4'),'-i',str(out/'mezcla.wav'),'-map','0:v:0','-map','1:a:0','-vf','tpad=stop_mode=clone:stop_duration=1.8','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-t',str(duration),'-movflags','+faststart',str(out/'presentacion.mp4')],check=True)
subprocess.run([ff,'-v','error','-y','-i',str(out/'musica.wav'),'-c:a','libmp3lame','-b:a','192k',str(out/'musica.mp3')],check=True)
# A short preview starts on the integration scene, before the invitation.
subprocess.run([ff,'-v','error','-y','-ss','16.5','-i',str(out/'presentacion.mp4'),'-c:v','libx264','-crf','18','-c:a','aac','-b:a','192k','-movflags','+faststart',str(out/'cierre.mp4')],check=True)
with av.open(str(out/'presentacion.mp4')) as c:
 v=c.streams.video[0];assert (v.width,v.height)==(720,1280) and float(v.average_rate)==30
 assert len(c.streams.audio)==1 and len(c.streams.subtitles)==0
 count=0
 for frame in c.decode(video=0):
  if count==677:frame.to_image().save(out/'cierre.jpg',quality=94)
  count+=1
 assert count==678
with av.open(str(out/'presentacion.mp4')) as c:assert sum(1 for _ in c.decode(audio=0))>0
peak=float(np.max(np.abs(decode(out/'presentacion.mp4'))));assert peak<.99
# The lossless voice/effects mix remains unchanged throughout its 20.8 s timeline.
orig=decode(dry/'mezcla-sin-musica.wav');assert np.max(np.abs((mix-music)[:len(orig)]-orig))<1e-6
music_db={}
for a,b in [(17.98,19.8),(19.85,20.3),(20.3,21.3),(21.3,22.3)]:
 s=music[round(a*rate):round(b*rate)];music_db[f'{a}-{b}']=round(float(20*np.log10(np.sqrt(np.mean(s*s))+1e-12)),2)
validation={'all_passed':True,'duration':duration,'frames':count,'fps':30,'size':[720,1280],'full_video_decode':True,'full_audio_decode':True,'subtitle_streams':0,'peak_after_aac':peak,'voice_and_effects_unchanged':True,'music_source':'Approved v10, original uninterrupted timing','music_generation':False,'new_provider_calls':0,'new_provider_credits':0,'closing_hold_added_seconds':1.8,'cadence_lift_db':round(float(20*np.log10(1.2)),3),'music_rms_dbfs':music_db,'instrument_synthesis':False,'musical_edit':'Restore original cadence and natural tail, no new chord or cymbal added'}
(out/'validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n')
(out/'README.md').write_text('''# Nienfos · Final musical recuperado

[Ver presentación](presentacion.mp4) · [Ver solamente el cierre](cierre.mp4) · [Escuchar la música](musica.mp3)

22,6 segundos · 720×1280 · 30 fps · sin subtítulos.

El recorte anterior saltaba desde 17,8 hasta 21,3 segundos de la canción: la invitación final quedaba acompañada por una cola ya muy tenue. Ahora continúa la interpretación original del trío y se recupera su cadencia cerca del segundo 20, inmediatamente después de la última frase. Una subida suave de 1,58 dB después de la voz da presencia al final musical. El logo permanece 1,8 segundos adicionales y deja sonar la resonancia de la grabación.

Se reutilizó el cierre ya interpretado en la canción aprobada. No se sintetizó un acorde nuevo ni se añadieron platillos artificiales; no se afirma que la armonía sea una séptima específica. La voz, su texto, sus tiempos y los efectos conservan su mezcla original. Las escenas siguen iguales; solamente se sostiene el último fotograma al final.

Trabajo realizado mediante edición y mezcla local: 0 llamadas externas y 0 créditos adicionales de ElevenLabs. Verificación instrumental de duración, decodificación, continuidad de la música, preservación de voz y niveles sin saturación; no se declara escucha humana.

![Cierre](cierre.jpg)

[Validación](validation.json) · [Versión anterior](../nienfos-presentacion-v13-kanban/presentacion.mp4)
''')
print(json.dumps(validation,ensure_ascii=False))
