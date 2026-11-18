from pathlib import Path
import json,hashlib
import av
import numpy as np
from PIL import Image,ImageDraw,ImageFont
root=Path(__file__).resolve().parents[3]
out=root/'reports/videos/nienfos-presentacion-v3'
movie=out/'presentacion.mp4'
scenes=[('Presentación',0,90),('Escuchamos',90,105),('Diseñamos',195,105),('Desarrollamos',300,105),('Clientes',405,105),('Conversemos',510,90)]
targets={45:'portada.jpg'}
for i,(_,start,n) in enumerate(scenes):
 targets[start+n//2]=f'escena-{i+1}.jpg'
 targets[start+25]=f'movimiento-{i+1}-a.jpg'
 targets[start+65]=f'movimiento-{i+1}-b.jpg'
 # Two samples during each overlapping wipe.
 if i:targets[start+5]=f'transicion-{i}-a.jpg';targets[start+12]=f'transicion-{i}-b.jpg'
pics={}
with av.open(str(movie)) as c:
 assert len(c.streams.audio)==0
 s=c.streams.video[0];assert (s.width,s.height)==(720,1280)
 assert float(s.average_rate)==30
 duration=float(s.duration*s.time_base);assert abs(duration-20)<.01
 n=0
 for frame in c.decode(video=0):
  if n in targets:
   im=frame.to_image();pics[targets[n]]=im;im.save(out/targets[n],quality=93)
   if n==45:im.save(out/'portada.jpg',quality=93)
  n+=1
 assert n==600
font=ImageFont.truetype('/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf',15)
board=Image.new('RGB',(1440,470),'#e5ebe8');draw=ImageDraw.Draw(board)
for i,(name,start,n) in enumerate(scenes):
 im=pics[f'escena-{i+1}.jpg'].copy();im.thumbnail((240,427));board.paste(im,(i*240,35));draw.text((i*240+10,8),name,font=font,fill='#142a32')
board.save(out/'escenas.jpg',quality=93)
board=Image.new('RGB',(1200,890),'#e5ebe8');draw=ImageDraw.Draw(board)
for i in range(1,6):
 for j,letter in enumerate('ab'):
  im=pics[f'transicion-{i}-{letter}.jpg'].copy();im.thumbnail((240,427));board.paste(im,((i-1)*240,j*445+18));draw.text(((i-1)*240+8,j*445),f'Barrido {i} · {letter}',font=font,fill='#142a32')
board.save(out/'transiciones.jpg',quality=92)
motion=[]
for i,(name,start,n) in enumerate(scenes):
 a=np.array(pics[f'movimiento-{i+1}-a.jpg'].resize((180,320))).astype(float)
 b=np.array(pics[f'movimiento-{i+1}-b.jpg'].resize((180,320))).astype(float)
 delta=float(np.mean(np.abs(a-b)));assert delta>.1,(name,delta)
 motion.append({'scene':name,'mean_pixel_difference':round(delta,3)})
validation={'duration':duration,'frames':600,'size':[720,1280],'fps':30,'audio_streams':0,'full_decode':True,'movement_per_scene':motion,'all_passed':True,'sha256':hashlib.sha256(movie.read_bytes()).hexdigest()}
(out/'validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n')
(out/'README.md').write_text('''# Nienfos · Presentación, revisión 03

[Reproducir la presentación](presentacion.mp4)

20 segundos · vertical 720×1280 · 30 fps · **sin pistas de audio**.

- Fondo continuo de cuadrados y rectángulos, con desplazamiento, perspectiva y cambios suaves de escala.
- Se conservan las escenas blancas y el cierre de marca.
- El proceso se muestra en movimiento: las necesidades se ordenan, el diseño se construye por partes y las herramientas se conectan.
- Chrem y RD aparecen juntos en dos imágenes más pequeñas, con más espacio para el fondo.

![Las seis escenas](escenas.jpg)

[Ver los barridos entre escenas](transiciones.jpg) · [Validación del archivo](validation.json)

Se usan la marca y capturas públicas reales de Nienfos. Las animaciones del proceso son ilustraciones explicativas, no una grabación de un producto. RD muestra únicamente su acceso público. Se conservó la [presentación anterior](../nienfos-10-profesional/10/video.mp4).
''')
print(json.dumps(validation,ensure_ascii=False))
