"""Explicitly requested composite: v17 Nosotros + v15 te damos la solución."""
from pathlib import Path
import subprocess,json,hashlib,shutil
import numpy as np
import av,imageio_ffmpeg
root=Path(__file__).resolve().parents[3];out=root/'reports/videos/nienfos-presentacion-v18-toma-combinada';out.mkdir(parents=True,exist_ok=True)
latest=root/'reports/videos/nienfos-presentacion-v17-locucion-natural';earlier=root/'reports/videos/nienfos-presentacion-v15-solucion'
ff=imageio_ffmpeg.get_ffmpeg_exe();rate=44100;start=round(17.98*rate);n=772*1470;duration=772/30

def decode(p,filters=None):
 args=[ff,'-v','error','-i',str(p),'-ar',str(rate),'-ac','2']
 if filters:args+=['-af',filters]
 return np.frombuffer(subprocess.check_output(args+['-f','f32le','pipe:1']),dtype='<f4').reshape(-1,2).copy()
def save(name,a):
 p=out/(name+'.f32');p.write_bytes(a.astype('<f4').tobytes());subprocess.run([ff,'-v','error','-y','-f','f32le','-ar',str(rate),'-ac','2','-i',str(p),'-c:a','pcm_s24le',str(out/(name+'.wav'))],check=True);p.unlink()
a=decode(latest/'narracion.wav');b=decode(earlier/'narracion.wav')
# End the latest prefix inside the native quiet interval 2.95..3.30 s,
# after the complete final /s/ in Nosotros; resume the earlier take before /t/.
new_cut=start+round(3.18*rate);old_resume=start+round(2.35*rate)
old_end=start+len(decode(earlier/'frase-final.mp3'))
suffix=b[old_resume:min(old_end,len(b))].copy()
voice=np.zeros((n,2),dtype=np.float32);voice[:new_cut]=a[:new_cut];voice[new_cut:new_cut+len(suffix)]=suffix
f=44;voice[new_cut-f:new_cut]*=np.linspace(1,0,f)[:,None];voice[new_cut:new_cut+f]*=np.linspace(0,1,f)[:,None]
# Prove the last Nosotros (including s) and previous ending are retained exactly.
assert np.array_equal(voice[:new_cut-f],a[:new_cut-f])
assert np.array_equal(voice[new_cut+f:new_cut+len(suffix)],b[old_resume+f:old_resume+len(suffix)])
prefix_gap=a[start+round(3.05*rate):start+round(3.18*rate)]
assert np.sqrt(np.mean(prefix_gap*prefix_gap))<.004
voice_end=np.flatnonzero(np.max(np.abs(voice),axis=1)>.003)[-1]/rate
previous=json.loads((latest/'validation.json').read_text());old_cadence=previous['final_music_hit_seconds'];target=voice_end+.28;speed=old_cadence/target
music=decode(latest/'musica.wav',filters=f'atempo={speed:.12f}');music=np.pad(music,((0,max(0,n-len(music))),(0,0)))[:n]
fx=decode(latest/'mezcla-sin-musica.wav')-a
mix=voice+fx+music;assert np.isfinite(mix).all() and np.max(np.abs(mix))<.94
save('narracion',voice);save('mezcla',mix);save('mezcla-sin-musica',voice+fx)
subprocess.run([ff,'-v','error','-y','-ss','17.98','-i',str(out/'narracion.wav'),'-t','5.1','-c:a','libmp3lame','-b:a','192k',str(out/'frase-final.mp3')],check=True)
for name,track in [('presentacion','mezcla.wav'),('presentacion-sin-musica','mezcla-sin-musica.wav')]:
 subprocess.run([ff,'-v','error','-y','-i',str(latest/'visual-sin-audio.mp4'),'-i',str(out/track),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k','-t',str(duration),'-movflags','+faststart',str(out/(name+'.mp4'))],check=True)
subprocess.run([ff,'-v','error','-y','-ss','17.6','-i',str(out/'presentacion.mp4'),'-c:v','libx264','-crf','18','-c:a','aac','-b:a','192k','-movflags','+faststart',str(out/'cierre.mp4')],check=True)
def video_hash(path):
 h=hashlib.sha256()
 with av.open(str(path)) as c:
  for p in c.demux(video=0):h.update(bytes(p))
 return h.hexdigest()
assert video_hash(out/'presentacion.mp4')==video_hash(latest/'presentacion.mp4')
with av.open(str(out/'presentacion.mp4')) as c:
 v=c.streams.video[0];assert (v.width,v.height)==(720,1280) and float(v.average_rate)==30
 assert len(c.streams.audio)==1 and len(c.streams.subtitles)==0
 count=sum(1 for _ in c.decode(video=0));assert count==772
with av.open(str(out/'presentacion.mp4')) as c:assert sum(1 for _ in c.decode(audio=0))>0
peak=float(np.max(np.abs(decode(out/'presentacion.mp4'))));assert peak<.99
validation={'all_passed':True,'duration':duration,'frames':count,'fps':30,'size':[720,1280],'full_video_decode':True,'full_audio_decode':True,'video_packets_identical_to_v17':True,'subtitle_streams':0,'nosotros_source':'v17','nosotros_prefix_retained_through_seconds':3.18,'prefix_samples_identical_except_last_ms':True,'ending_source':'v15','earlier_take_resume_seconds':2.35,'ending_samples_identical_except_first_ms':True,'join_inside_native_pause':True,'inserted_silence_seconds':0,'voice_speed_unchanged':True,'voice_end_seconds':round(voice_end,3),'cadence_seconds':round(target,3),'cadence_after_voice_seconds':.28,'music_local_tempo_factor':speed,'music_pitch_preserved':True,'peak_after_aac':peak,'new_provider_calls':0,'new_provider_credits':0}
(out/'validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n');shutil.copy2(latest/'cierre.jpg',out/'cierre.jpg')
(out/'README.md').write_text('''# Nienfos · Cierre con las dos tomas elegidas

[Ver presentación](presentacion.mp4) · [Ver solo el cierre](cierre.mp4) · [Escuchar solo la frase](frase-final.mp3)

Se conserva «Contanos qué tenés en mente. Nosotros» de la última toma (v17), incluida la s final completa y parte de su pausa natural. La unión se realiza a los 3,18 s de esa toma, dentro del silencio. Desde allí se utiliza «te damos la solución» de la toma anterior (v15), retomándola a los 2,350 s, antes de la t. Los bordes se suavizan durante 1 ms y no se añaden silencios artificiales.

Se verificó igualdad de las muestras con las tomas seleccionadas fuera de esos bordes. La voz conserva tono y velocidad. Se ajustó localmente el tiempo de la música para que el platillo aprobado entre después de la última palabra. Las imágenes son idénticas al video anterior y siguen sin numeración ni subtítulos.

25,73 segundos · 720×1280 · 30 fps. **0 llamadas a API y 0 créditos adicionales**.

![Cierre](cierre.jpg)

[Validación técnica](validation.json) · [Sin música](presentacion-sin-musica.mp4)

Las medidas y comprobaciones de muestras documentan la edición; no sustituyen una escucha humana.
''')
print(json.dumps(validation,ensure_ascii=False))
