"""Existing speech only: insert a short pause, remove scene numbering, retime music locally."""
from pathlib import Path
import subprocess,json
import numpy as np
import av,imageio_ffmpeg
root=Path(__file__).resolve().parents[3];out=root/'reports/videos/nienfos-presentacion-v16-pausa';out.mkdir(parents=True,exist_ok=True);old=root/'reports/videos/nienfos-presentacion-v15-solucion'
ff=imageio_ffmpeg.get_ffmpeg_exe();rate=44100;fps=30;frames_expected=745;duration=frames_expected/fps;n=frames_expected*1470;pause=7*1470

def decode(p,filters=None):
 args=[ff,'-v','error','-i',str(p),'-ar',str(rate),'-ac','2']
 if filters:args+=['-af',filters]
 return np.frombuffer(subprocess.check_output(args+['-f','f32le','pipe:1']),dtype='<f4').reshape(-1,2).copy()
def save(name,a):
 p=out/(name+'.f32');p.write_bytes(a.astype('<f4').tobytes());subprocess.run([ff,'-v','error','-y','-f','f32le','-ar',str(rate),'-ac','2','-i',str(p),'-c:a','pcm_s24le',str(out/(name+'.wav'))],check=True);p.unlink()
voice_old=decode(old/'narracion.wav');speech_start=round(17.98*rate)
# Low-energy gap after the sibilant in Nosotros, just before the /t/ in te.
# ASR word times are approximate: constrain to the actual measured quiet gap.
mono=np.mean(voice_old,axis=1);choices=range(speech_start+round(2.355*rate),speech_start+round(2.369*rate))
cut=min(choices,key=lambda i:float(np.mean(mono[i-44:i+44]**2)))
voice=np.concatenate([voice_old[:cut],np.zeros((pause,2),dtype=np.float32),voice_old[cut:]])
# 1 ms fades at low-energy edit boundaries suppress discontinuities.
f=44;voice[cut-f:cut]*=np.linspace(1,0,f)[:,None];voice[cut+pause:cut+pause+f]*=np.linspace(0,1,f)[:,None]
assert len(voice)==n
assert np.array_equal(voice[:cut-f],voice_old[:cut-f])
assert np.array_equal(voice[cut+pause+f:],voice_old[cut+f:])
fx=decode(old/'mezcla-sin-musica.wav')-voice_old;fx=np.pad(fx,((0,pause),(0,0)))
# Less than 1% tempo adjustment with native pitch, to move the approved cadence after the added pause.
speed=24.6/duration
music=decode(old/'musica.wav',filters=f'atempo={speed:.12f}')
music=np.pad(music,((0,max(0,n-len(music))),(0,0)))[:n]
fade=round(.04*rate);music[-fade:]*=np.linspace(1,0,fade)[:,None]
mix=voice+fx+music;assert np.isfinite(mix).all() and np.max(np.abs(mix))<.94
save('narracion',voice);save('musica',music);save('mezcla',mix);save('mezcla-sin-musica',voice+fx)
# Independent voice preview for local word checking, with no music interference.
subprocess.run([ff,'-v','error','-y','-ss','17.98','-i',str(out/'narracion.wav'),'-t','4.3','-c:a','pcm_s16le',str(out/'frase-final.wav')],check=True)
for name,track in [('presentacion','mezcla.wav'),('presentacion-sin-musica','mezcla-sin-musica.wav')]:
 subprocess.run([ff,'-v','error','-y','-i',str(out/'visual-sin-audio.mp4'),'-i',str(out/track),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k','-t',str(duration),'-movflags','+faststart',str(out/(name+'.mp4'))],check=True)
subprocess.run([ff,'-v','error','-y','-ss','17.6','-i',str(out/'presentacion.mp4'),'-c:v','libx264','-crf','18','-c:a','aac','-b:a','192k','-movflags','+faststart',str(out/'cierre.mp4')],check=True)
with av.open(str(out/'presentacion.mp4')) as c:
 v=c.streams.video[0];assert (v.width,v.height)==(720,1280) and float(v.average_rate)==30
 assert len(c.streams.audio)==1 and len(c.streams.subtitles)==0
 count=0
 for frame in c.decode(video=0):
  if count in (75,235,350,495,710):frame.to_image().save(out/f'escena-{count}.jpg',quality=94)
  count+=1
 assert count==frames_expected
with av.open(str(out/'presentacion.mp4')) as c:assert sum(1 for _ in c.decode(audio=0))>0
peak=float(np.max(np.abs(decode(out/'presentacion.mp4'))));assert peak<.99
s=(root/'scripts/local_video/remotion/src/PresentationV16.tsx').read_text();assert "String(i+1).padStart" not in s and ' / 05' not in s
end=np.flatnonzero(np.max(np.abs(voice),axis=1)>.003)[-1]/rate;cadence=22.05/speed
validation={'all_passed':True,'duration':duration,'frames':count,'size':[720,1280],'fps':30,'full_video_decode':True,'full_audio_decode':True,'subtitle_streams':0,'pause_added_seconds':pause/rate,'speech_cut_relative_seconds':round((cut-speech_start)/rate,5),'voice_speed_unchanged':True,'voice_samples_outside_edit_identical':True,'scene_counter_removed':True,'music_speed_factor':speed,'music_pitch_preserved':True,'voice_end_seconds':round(end,3),'cadence_seconds':round(cadence,3),'cadence_after_voice_seconds':round(cadence-end,3),'peak_after_aac':peak,'new_provider_calls':0,'new_provider_credits':0}
(out/'validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n')
(out/'README.md').write_text('''# Nienfos · Pausa breve y sin contador

[Ver presentación](presentacion.mp4) · [Ver solo el cierre](cierre.mp4)

Se agregaron 0,23 segundos de pausa entre «Nosotros» y «te damos la solución», editando la grabación existente. Se conserva la velocidad y el texto de la voz. Los bordes del corte se suavizan durante 1 ms.

Se eliminó el contador 01 / 05, 02 / 05, etc., de las cinco escenas. Las pantallas, el tablero, los flujos y la composición restante se conservan.

La música se ajustó localmente menos de un 1% en tempo, conservando el tono, para que su golpe final siga entrando después de la locución. Duración final: 24,83 segundos. Sin subtítulos. Sin nuevas generaciones: 0 llamadas y 0 créditos adicionales de ElevenLabs.

![Cierre sin numeración](escena-710.jpg)

[Sin música](presentacion-sin-musica.mp4) · [Validación](validation.json) · [Versión anterior](../nienfos-presentacion-v15-solucion/presentacion.mp4)

Verificación instrumental de imagen y audio, duración, conservación de muestras de voz fuera del corte y niveles sin saturación. No se declara escucha humana.
''')
print(json.dumps(validation,ensure_ascii=False))
