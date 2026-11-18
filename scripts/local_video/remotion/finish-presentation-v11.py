from pathlib import Path
import json,subprocess,hashlib
import numpy as np
import av,imageio_ffmpeg
from PIL import Image,ImageDraw,ImageFont
root=Path(__file__).resolve().parents[3];out=root/'reports/videos/nienfos-presentacion-v11-historia';old=root/'reports/videos/nienfos-presentacion-v10-groove'
ffmpeg=imageio_ffmpeg.get_ffmpeg_exe();rate=44100

def decode(path):
 raw=subprocess.check_output([ffmpeg,'-v','error','-i',str(path),'-ar',str(rate),'-ac','2','-f','f32le','pipe:1']);return np.frombuffer(raw,dtype='<f4').copy().reshape(-1,2)
approved_master=decode(old/'mezcla.wav');old_dry=decode(old/'mezcla-sin-musica.wav');new_dry=decode(out/'mezcla-sin-musica.wav')
assert approved_master.shape==old_dry.shape==new_dry.shape
music=approved_master-old_dry
mixed=new_dry+music
assert np.isfinite(mixed).all() and np.max(np.abs(mixed))<.97
raw=out/'mezcla.f32';raw.write_bytes(mixed.astype('<f4').tobytes())
subprocess.run([ffmpeg,'-v','error','-y','-f','f32le','-ar',str(rate),'-ac','2','-i',str(raw),'-c:a','pcm_s24le',str(out/'mezcla.wav')],check=True);raw.unlink()
movie=out/'presentacion.mp4'
subprocess.run([ffmpeg,'-v','error','-y','-i',str(out/'visual-sin-audio.mp4'),'-i',str(out/'mezcla.wav'),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k','-t','24.3','-movflags','+faststart',str(movie)],check=True)
scenes=[('Portada actual',0,113),('Entender la necesidad',113,135),('Boceto a solución',248,141),('Conectar la operación',389,145),('Cierre directo',534,195)]
targets={}
for i,(_,start,n) in enumerate(scenes):
 for tag,f in [('entrada',30),('medio',65),('completo',min(175 if i==4 else 110,n-8))]:targets[start+f]=f'escena-{i+1}-{tag}.jpg'
 if i:targets[start+7]=f'transicion-{i}.jpg'
font=ImageFont.truetype('/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf',14)
images={}
with av.open(str(movie)) as c:
 assert len(c.streams.video)==1 and len(c.streams.audio)==1 and len(c.streams.subtitles)==0
 stream=c.streams.video[0];assert (stream.width,stream.height)==(720,1280) and float(stream.average_rate)==30
 duration=float(stream.duration*stream.time_base);assert abs(duration-24.3)<.03
 count=0
 for frame in c.decode(video=0):
  if count in targets:
   im=frame.to_image();images[targets[count]]=im;im.save(out/targets[count],quality=93)
  if count==45:frame.to_image().save(out/'portada.jpg',quality=93)
  count+=1
 assert count==729
with av.open(str(movie)) as c:assert sum(1 for _ in c.decode(audio=0))>0
peak=float(np.max(np.abs(decode(movie))));assert peak<.99
board=Image.new('RGB',(1200,470),'#e5ebe8');draw=ImageDraw.Draw(board)
for i,(title,_,_) in enumerate(scenes):
 im=images[f'escena-{i+1}-completo.jpg'].copy();im.thumbnail((240,427));board.paste(im,(240*i,35));draw.text((240*i+9,8),title,font=font,fill='#142a32')
board.save(out/'escenas.jpg',quality=94)
timeline=Image.new('RGB',(1200,1395),'#e5ebe8');draw=ImageDraw.Draw(timeline)
for row,tag in enumerate(['entrada','medio','completo']):
 for i,(_,_,_) in enumerate(scenes):
  im=images[f'escena-{i+1}-{tag}.jpg'].copy();im.thumbnail((240,427));timeline.paste(im,(i*240,row*465+30));draw.text((i*240+8,row*465+6),f'{i+1} / {tag}',font=font,fill='#142a32')
timeline.save(out/'historia-en-movimiento.jpg',quality=93)
# Audio equality is checked in the lossless domain before the final AAC export.
music_residual=float(np.max(np.abs((mixed-new_dry)-music)))
assert music_residual<1e-6
validation={'all_passed':True,'frames':count,'duration':duration,'size':[720,1280],'audio_streams':1,'subtitle_streams':0,'full_video_decode':True,'full_audio_decode':True,'peak_after_aac':round(peak,5),'voice_reused':True,'music_reused_without_gain_or_timing_change':True,'music_equality_max_error':music_residual,'new_external_model_calls':0,'new_provider_credits':0,'new_site_capture':'https://dev.nienfos.com/','brand_url_in_video':'nienfos.com','removed_visual_section':'Ideas que ya son proyectos / clientes','spoken_script_unchanged':True,'scenes':[{'name':s[0],'start_frame':s[1],'frames':s[2]} for s in scenes]}
(out/'validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n')
(out/'README.md').write_text('''# Nienfos · Una historia visual más dinámica

[Ver presentación](presentacion.mp4)

24,3 segundos · 720×1280 · 30 fps · Mauricio y música de la versión anterior · sin subtítulos.

1. Portada actual capturada de dev.nienfos.com, presentada con la dirección nienfos.com.
2. Necesidades y formas de trabajo se reúnen alrededor del negocio y llevan a un alcance claro.
3. Un boceto se construye, recibe una devolución y revela la portada real con su vista móvil.
4. Herramientas distribuidas se conectan a un núcleo y muestran circulación de información.
5. Cierre blanco directo con marca y enlace, sin placa de clientes ni título «Ideas que ya son proyectos».

![Escenas](escenas.jpg)

[Ver la evolución de las escenas](historia-en-movimiento.jpg)

Se reutilizan íntegramente la locución y la música aprobadas, con sus niveles y tiempos. Esto conserva también la frase hablada «Ideas que ya son proyectos reales», ahora sobre el cierre; se retiró su placa visual. Los mismos efectos se reubicaron según los movimientos nuevos. No hubo nuevas generaciones de voz, música ni efectos ni llamadas a APIs de modelos. El navegador solo consultó el sitio público para las capturas.

La captura utiliza el sitio de desarrollo solicitado; se ocultan únicamente el distintivo DEV y los controles flotantes de chat y pausa de movimiento para la presentación. No se modificó la web. [Captura de escritorio](source/desktop.png) · [Original sin ocultar controles](source/desktop-raw.png) · [Captura móvil](source/mobile.png) · [Procedencia](source/desktop.json).

Los mapas, conexiones y el boceto son animaciones explicativas del proceso, no una grabación de una aplicación privada.

[Validación técnica](validation.json) · [Tiempos de efectos](sound-plan.json) · [Versión anterior](../nienfos-presentacion-v10-groove/presentacion.mp4)
''')
print(json.dumps(validation,ensure_ascii=False))
