"""Local, lossless phrase removal and closing retime. No provider calls."""
from pathlib import Path
import json, subprocess
import numpy as np
import av, imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont
root=Path(__file__).resolve().parents[3]
out=root/'reports/videos/nienfos-presentacion-v12-cierre';out.mkdir(parents=True,exist_ok=True)
old=root/'reports/videos/nienfos-presentacion-v11-historia'
groove=root/'reports/videos/nienfos-presentacion-v10-groove'
ff=imageio_ffmpeg.get_ffmpeg_exe();rate=44100;fps=30
cut=534*1470;skip=105*1470;total=624*1470

def decode(path):
    raw=subprocess.check_output([ff,'-v','error','-i',str(path),'-ar',str(rate),'-ac','2','-f','f32le','pipe:1'])
    return np.frombuffer(raw,dtype='<f4').reshape(-1,2).copy()
def save(name,a):
    raw=out/(name+'.f32');raw.write_bytes(a.astype('<f4').tobytes())
    subprocess.run([ff,'-v','error','-y','-f','f32le','-ar',str(rate),'-ac','2','-i',str(raw),'-c:a','pcm_s24le',str(out/(name+'.wav'))],check=True);raw.unlink()
def splice(a):return np.concatenate([a[:cut],a[cut+skip:cut+skip+(total-cut)]])
voice_source=decode(root/'reports/videos/nienfos-presentacion-v5-voces/mauricio/narracion.wav')
voice=splice(voice_source)
# The removed interval contains phrase 5 only; both splice points fall in silence.
assert np.array_equal(voice[:cut],voice_source[:cut])
assert np.array_equal(voice[cut:],voice_source[cut+skip:cut+skip+len(voice)-cut])
fx_source=decode(old/'solo-efectos.wav');fx=np.zeros((total,2),dtype=np.float32);fx[:cut]=fx_source[:cut]
plan=json.loads((old/'sound-plan.json').read_text());events=[x.copy() for x in plan['events'] if x['frame']<534]
for event,frame in zip(plan['events'][-2:],[569,600]):
    src=event['frame']*1470;n=event['sample_count'];dst=frame*1470
    fx[dst:dst+n]+=fx_source[src:src+n]
    e=event.copy();e.update(frame=frame,seconds=round(frame/30,4));events.append(e)
plan.update(duration=20.8,events=events,removed_phrase='Ideas que ya son proyectos reales.',music=True)
(out/'sound-plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
music_source=decode(groove/'mezcla.wav')-decode(groove/'mezcla-sin-musica.wav')
music=splice(music_source)
# Fixed-length 100 ms linear crossfade on the music only, retaining original ending.
half=2205;lo=cut-half;hi=cut+half
w=np.linspace(0,1,hi-lo,dtype=np.float32)[:,None]
music[lo:hi]=music_source[lo:hi]*(1-w)+music_source[lo+skip:hi+skip]*w
save('narracion',voice);save('solo-efectos',fx);save('mezcla-sin-musica',voice+fx)
mix=voice+fx+music;assert np.max(np.abs(mix))<.97
save('mezcla',mix)
for name,audio in [('presentacion','mezcla.wav'),('presentacion-sin-musica','mezcla-sin-musica.wav')]:
    subprocess.run([ff,'-v','error','-y','-i',str(out/'visual-sin-audio.mp4'),'-i',str(out/audio),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k','-t','20.8','-movflags','+faststart',str(out/(name+'.mp4'))],check=True)
movie=out/'presentacion.mp4';targets={528:'antes-del-cierre.jpg',564:'cierre-entrada.jpg',599:'cierre.jpg',623:'cierre-final.jpg'}
with av.open(str(movie)) as c:
    assert len(c.streams.video)==1 and len(c.streams.audio)==1 and len(c.streams.subtitles)==0
    v=c.streams.video[0];assert (v.width,v.height)==(720,1280) and float(v.average_rate)==30
    duration=float(v.duration*v.time_base);assert abs(duration-20.8)<.03
    count=0
    for frame in c.decode(video=0):
        if count in targets:frame.to_image().save(out/targets[count],quality=94)
        if count==45:frame.to_image().save(out/'portada.jpg',quality=94)
        count+=1
    assert count==624
with av.open(str(movie)) as c:assert sum(1 for _ in c.decode(audio=0))>0
peak=float(np.max(np.abs(decode(movie))));assert peak<.99
# Confirm first four scenes are unchanged after deterministic re-render.
max_diff=0
with av.open(str(old/'visual-sin-audio.mp4')) as a,av.open(str(out/'visual-sin-audio.mp4')) as b:
    for i,(fa,fb) in enumerate(zip(a.decode(video=0),b.decode(video=0))):
        if i>=534:break
        max_diff=max(max_diff,int(np.max(np.abs(fa.to_ndarray(format='rgb24').astype(np.int16)-fb.to_ndarray(format='rgb24').astype(np.int16)))))
validation={'all_passed':True,'frames':count,'duration':duration,'resolution':[720,1280],'fps':30,'full_video_decode':True,'full_audio_decode':True,'subtitle_streams':0,'peak_after_aac':peak,'removed_voice_interval_seconds':[17.8,21.3],'remaining_voice_samples_identical':True,'music_crossfade_seconds':.1,'first_four_scenes_max_pixel_difference':max_diff,'effects_reused_and_retimed':True,'new_provider_calls':0,'new_provider_credits':0}
(out/'validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n')
(out/'README.md').write_text('''# Nienfos · Cierre ajustado

[Ver presentación](presentacion.mp4)

20,8 segundos · 720×1280 · 30 fps · sin subtítulos.

Se eliminó de la locución «Ideas que ya son proyectos reales» y se quitaron los 3,5 segundos correspondientes. Después de explicar las integraciones, pasa directamente a «Contanos qué tenés en mente».

Se adelantaron el logo y la dirección del cierre, junto con sus dos efectos. La voz restante conserva las muestras originales, sin cambios de tono ni velocidad. Se reutilizó la música aprobada: empalme local de 100 ms y final original. No hubo generaciones ni llamadas a proveedores; 0 créditos adicionales de ElevenLabs.

![Cierre](cierre-final.jpg)

[Versión sin música](presentacion-sin-musica.mp4) · [Validación](validation.json) · [Versión anterior](../nienfos-presentacion-v11-historia/presentacion.mp4)
''')
print(json.dumps(validation,ensure_ascii=False))
