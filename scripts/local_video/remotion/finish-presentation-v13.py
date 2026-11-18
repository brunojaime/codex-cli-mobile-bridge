"""Mux approved audio unchanged; validate and inspect the revised planning board."""
from pathlib import Path
import subprocess,json,hashlib
import av,imageio_ffmpeg
from PIL import Image,ImageDraw,ImageFont
root=Path(__file__).resolve().parents[3];out=root/'reports/videos/nienfos-presentacion-v13-kanban';old=root/'reports/videos/nienfos-presentacion-v12-cierre'
ff=imageio_ffmpeg.get_ffmpeg_exe()
for name in ['presentacion','presentacion-sin-musica']:
 subprocess.run([ff,'-v','error','-y','-i',str(out/'visual-sin-audio.mp4'),'-i',str(old/(name+'.mp4')),'-map','0:v:0','-map','1:a:0','-c','copy','-movflags','+faststart',str(out/(name+'.mp4'))],check=True)
def audio_hash(path):
 h=hashlib.sha256()
 with av.open(str(path)) as c:
  for f in c.decode(audio=0):h.update(f.to_ndarray().tobytes())
 return h.hexdigest()
assert audio_hash(out/'presentacion.mp4')==audio_hash(old/'presentacion.mp4')
frames={45:'portada.jpg',138:'tablero-inicio.jpg',170:'tablero-avance.jpg',235:'tablero-acordado.jpg',350:'web-conservada.jpg',495:'flujo-integracion.jpg',623:'cierre.jpg'}
with av.open(str(out/'presentacion.mp4')) as c:
 v=c.streams.video[0];assert (v.width,v.height)==(720,1280) and float(v.average_rate)==30
 assert len(c.streams.audio)==1 and len(c.streams.subtitles)==0
 duration=float(v.duration*v.time_base);assert abs(duration-20.8)<.03
 n=0
 for frame in c.decode(video=0):
  if n in frames:frame.to_image().save(out/frames[n],quality=94)
  n+=1
 assert n==624
font=ImageFont.truetype('/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf',17)
board=Image.new('RGB',(1200,568),'#e5ebe8');d=ImageDraw.Draw(board)
for i,(name,label) in enumerate([('tablero-inicio.jpg','Necesidades'),('tablero-avance.jpg','Priorizamos'),('tablero-acordado.jpg','Acordamos'),('flujo-integracion.jpg','Integración')]):
 im=Image.open(out/name);im.thumbnail((300,533));board.paste(im,(i*300,35));d.text((i*300+12,8),label,fill='#142a32',font=font)
board.save(out/'etapas.jpg',quality=94)
# Source-level guards protect the web/phone captures and their animations.
src=root/'scripts/local_video/remotion/src'
a=(src/'PresentationV12.tsx').read_text();b=(src/'PresentationV13.tsx').read_text()
for start,end in [('const Browser:','const Discovery:'),('const Design:','const Integration:'),('const Integration:','const Closing:'),('const Closing:','const Shot:')]:
 assert a[a.index(start):a.index(end)].strip()==b[b.index(start):b.index(end)].strip() if start!='const Browser:' else a[a.index(start):a.index(end)].strip()==b[b.index(start):b.index('// Alcance:')].strip()
validation={'all_passed':True,'frames':n,'duration':duration,'size':[720,1280],'fps':30,'full_video_decode':True,'full_audio_decode':True,'audio_identical_to_v12':True,'audio_sha256':audio_hash(out/'presentacion.mp4'),'subtitle_streams':0,'browser_and_mobile_animation_source_unchanged':True,'integration_and_closing_source_unchanged':True,'changed_scene':'Alcance: tablero Kanban','new_provider_calls':0,'new_provider_credits':0}
(out/'validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n')
plan=json.loads((old/'sound-plan.json').read_text());plan['events'][1]['reason']='El primer papelito avanza de necesidades a prioridades.';plan['events'][2]['reason']='Avanza la forma de trabajar en el tablero.';plan['events'][3]['reason']='Se acuerda un alcance claro.'
(out/'sound-plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
(out/'README.md').write_text('''# Nienfos · Etapas visuales distintas

[Ver presentación](presentacion.mp4)

20,8 segundos · 720×1280 · 30 fps · sin subtítulos.

La etapa «Entender primero. Decidir mejor.» ahora utiliza un tablero Kanban: los papelitos de necesidad, proceso y equipo avanzan por Necesidades → Priorizamos → Acordamos y desembocan en un alcance claro. El movimiento explica el acuerdo del plan sin cambiar lo que dice la persona.

La integración mantiene su lenguaje de conexiones y circulación de información. Las pantallas de escritorio y móvil, sus movimientos y el cierre conservan su código anterior. El audio completo se copió sin recodificar: misma voz, texto, música y efectos, con idénticos tiempos. Los efectos existentes acompañan el avance del tablero. No hubo llamadas a proveedores ni consumo nuevo de créditos.

![Etapas distintas](etapas.jpg)

[Sin música](presentacion-sin-musica.mp4) · [Validación](validation.json) · [Versión anterior](../nienfos-presentacion-v12-cierre/presentacion.mp4)
''')
print(json.dumps(validation,ensure_ascii=False))
