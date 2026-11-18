"""Original standalone Contanos, followed by the already selected v18 composite."""
from pathlib import Path
import subprocess,json,hashlib,shutil
import numpy as np
import av,imageio_ffmpeg
root=Path(__file__).resolve().parents[3];out=root/'reports/videos/nienfos-presentacion-v19-contanos-original';out.mkdir(parents=True,exist_ok=True)
old=root/'reports/videos/nienfos-presentacion-v18-toma-combinada';original=root/'reports/videos/nienfos-presentacion-v12-cierre'
ff=imageio_ffmpeg.get_ffmpeg_exe();rate=44100;start=round(17.98*rate);n=772*1470;duration=772/30

def decode(p,filters=None):
 args=[ff,'-v','error','-i',str(p),'-ar',str(rate),'-ac','2']
 if filters:args+=['-af',filters]
 return np.frombuffer(subprocess.check_output(args+['-f','f32le','pipe:1']),dtype='<f4').reshape(-1,2).copy()
def save(name,a):
 p=out/(name+'.f32');p.write_bytes(a.astype('<f4').tobytes());subprocess.run([ff,'-v','error','-y','-f','f32le','-ar',str(rate),'-ac','2','-i',str(p),'-c:a','pcm_s24le',str(out/(name+'.wav'))],check=True);p.unlink()
a=decode(old/'narracion.wav');b=decode(original/'narracion.wav')
# The original standalone line is complete within 1.811 s; keep 1.95 s.
# The new take's Nosotros starts near 2.2 s; resume in quiet at 2.10 s.
dest=start+round(1.95*rate);resume=start+round(2.10*rate)
assert np.sqrt(np.mean(a[resume-220:resume+220]**2))<.004
assert np.sqrt(np.mean(b[dest-220:dest+220]**2))<.004
voice=np.zeros((n,2),dtype=np.float32);voice[:dest]=b[:dest];suffix=a[resume:];length=min(len(suffix),n-dest);voice[dest:dest+length]=suffix[:length]
f=44;voice[dest-f:dest]*=np.linspace(1,0,f)[:,None];voice[dest:dest+f]*=np.linspace(0,1,f)[:,None]
assert np.array_equal(voice[:dest-f],b[:dest-f])
assert np.array_equal(voice[dest+f:dest+length],a[resume+f:resume+length])
voice_end=np.flatnonzero(np.max(np.abs(voice),axis=1)>.003)[-1]/rate;target=voice_end+.28
previous=json.loads((old/'validation.json').read_text());speed=previous['cadence_seconds']/target
music_source=decode(old/'mezcla.wav')-decode(old/'mezcla-sin-musica.wav');save('musica-fuente',music_source)
music=decode(out/'musica-fuente.wav',filters=f'atempo={speed:.12f}');music=np.pad(music,((0,max(0,n-len(music))),(0,0)))[:n]
fx=decode(old/'mezcla-sin-musica.wav')-a;mix=voice+music+fx
assert np.isfinite(mix).all() and np.max(np.abs(mix))<.94
save('narracion',voice);save('mezcla',mix);save('mezcla-sin-musica',voice+fx)
subprocess.run([ff,'-v','error','-y','-ss','17.98','-i',str(out/'narracion.wav'),'-t','5.1','-c:a','libmp3lame','-b:a','192k',str(out/'frase-final.mp3')],check=True)
for name,track in [('presentacion','mezcla.wav'),('presentacion-sin-musica','mezcla-sin-musica.wav')]:
 subprocess.run([ff,'-v','error','-y','-i',str(old/'presentacion.mp4'),'-i',str(out/track),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k','-t',str(duration),'-movflags','+faststart',str(out/(name+'.mp4'))],check=True)
subprocess.run([ff,'-v','error','-y','-ss','17.6','-i',str(out/'presentacion.mp4'),'-c:v','libx264','-crf','18','-c:a','aac','-b:a','192k','-movflags','+faststart',str(out/'cierre.mp4')],check=True)
def video_hash(path):
 h=hashlib.sha256()
 with av.open(str(path)) as c:
  for p in c.demux(video=0):h.update(bytes(p))
 return h.hexdigest()
assert video_hash(out/'presentacion.mp4')==video_hash(old/'presentacion.mp4')
with av.open(str(out/'presentacion.mp4')) as c:
 v=c.streams.video[0];assert (v.width,v.height)==(720,1280) and float(v.average_rate)==30
 assert len(c.streams.audio)==1 and len(c.streams.subtitles)==0
 count=sum(1 for _ in c.decode(video=0));assert count==772
with av.open(str(out/'presentacion.mp4')) as c:assert sum(1 for _ in c.decode(audio=0))>0
peak=float(np.max(np.abs(decode(out/'presentacion.mp4'))));assert peak<.99
validation={'all_passed':True,'duration':duration,'frames':count,'fps':30,'size':[720,1280],'full_video_decode':True,'full_audio_decode':True,'video_packets_identical_to_v18':True,'subtitle_streams':0,'contanos_source':'Original v5 standalone phrase, via v12 lossless narration','original_contanos_complete':True,'nosotros_source':'v17, via v18 composite','ending_source':'v15, via v18 composite','selected_nosotros_and_ending_samples_preserved':True,'join_inside_silence':True,'voice_speed_unchanged':True,'voice_end_seconds':round(voice_end,3),'cadence_seconds':round(target,3),'cadence_after_voice_seconds':.28,'peak_after_aac':peak,'new_provider_calls':0,'new_provider_credits':0}
(out/'validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n');shutil.copy2(old/'cierre.jpg',out/'cierre.jpg')
(out/'README.md').write_text('''# Nienfos · Contanos original

[Ver presentación](presentacion.mp4) · [Ver solo el cierre](cierre.mp4) · [Escuchar solo la frase](frase-final.mp3)

Se recuperó «Contanos qué tenés en mente» de la grabación original, anterior a las dos regeneraciones de cierre. Se usa la versión sin pérdida conservada en v12, cuyo origen es la frase independiente de v5.

Se mantienen «Nosotros» completo de v17 y «te damos la solución» de v15, tal como quedaron unidos en v18. La unión nueva se realiza dentro del silencio anterior a «Nosotros», sin recortar sus sílabas. Se verificó la conservación de las muestras fuera de los bordes de 1 ms.

Las imágenes siguen idénticas, sin numeración ni subtítulos. El platillo se ajustó localmente para entrar después de la voz. 25,73 segundos · 720×1280 · 30 fps.

**0 llamadas a API y 0 créditos adicionales**.

![Cierre](cierre.jpg)

[Validación](validation.json) · [Sin música](presentacion-sin-musica.mp4) · [Versión anterior](../nienfos-presentacion-v18-toma-combinada/presentacion.mp4)

Las comprobaciones instrumentales no sustituyen una escucha humana.
''')
print(json.dumps(validation,ensure_ascii=False))
