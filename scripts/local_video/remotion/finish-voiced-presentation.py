from pathlib import Path
import json,subprocess,hashlib
import av,numpy as np,imageio_ffmpeg
from PIL import Image,ImageDraw,ImageFont
root=Path(__file__).resolve().parents[3]
out=root/'reports/videos/nienfos-presentacion-v5-voces'
plan=json.loads((out/'timing.json').read_text());m=json.loads((out/'narration.json').read_text())
ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
results=[];visual=out/'visual-sin-audio.mp4'
for v in m['voices']:
 folder=out/v['slug'];dest=folder/'presentacion.mp4'
 subprocess.run([ffmpeg,'-v','error','-y','-i',str(visual),'-i',str(folder/'narracion.wav'),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','160k','-movflags','+faststart','-t',str(plan['duration']),str(dest)],check=True)
 with av.open(str(dest)) as c:
  assert len(c.streams.video)==1 and len(c.streams.audio)==1 and len(c.streams.subtitles)==0
  s=c.streams.video[0];assert (s.width,s.height)==(720,1280) and float(s.average_rate)==30
  duration=float(s.duration*s.time_base);assert abs(duration-plan['duration'])<.04
  frames=sum(1 for _ in c.decode(video=0));assert frames==plan['total_frames']
 with av.open(str(dest)) as c:
  audio_frames=sum(1 for _ in c.decode(audio=0));assert audio_frames>0
 raw=subprocess.check_output([ffmpeg,'-v','error','-i',str(dest),'-vn','-ar','44100','-ac','1','-f','f32le','pipe:1'])
 a=np.frombuffer(raw,dtype='<f4');assert np.isfinite(a).all()
 peak=float(np.max(np.abs(a)));assert peak<.99,(v['name'],peak)
 rms=[]
 for i,start in enumerate(plan['starts']):
  offset=round((start/30+.18)*44100);n=round(plan['speech_seconds'][v['slug']][i]*44100)
  level=float(np.sqrt(np.mean(a[offset:offset+n]**2)));assert level>.01,(v['name'],i,level)
  assert .18+plan['speech_seconds'][v['slug']][i]<plan['frames'][i]/30
  rms.append(round(level,4))
 results.append({'voice':v['name'],'video':str(dest.relative_to(out)),'duration':duration,'frames':frames,'audio_streams':1,'subtitle_streams':0,'audio_peak':round(peak,4),'scene_speech_rms':rms,'full_video_decode':True,'full_audio_decode':True,'sha256':hashlib.sha256(dest.read_bytes()).hexdigest()})
 print('VERIFIED',v['name'],duration,'s; audio present, no subtitles',flush=True)
font=ImageFont.truetype('/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf',14)
board=Image.new('RGB',(1440,470),'#e5ebe8');draw=ImageDraw.Draw(board)
targets={plan['starts'][i]+min(plan['frames'][i]-10,108 if i in [1,2,3] else plan['frames'][i]//2):i for i in range(6)}
with av.open(str(visual)) as c:
 for n,frame in enumerate(c.decode(video=0)):
  if n in targets:
   i=targets[n];im=frame.to_image();im.save(out/f'escena-{i+1}.jpg',quality=92)
   if i==0:im.save(out/'portada.jpg',quality=92)
   im.thumbnail((240,427));board.paste(im,(i*240,35));draw.text((i*240+10,8),f'Escena {i+1} / {plan["starts"][i]/30:.2f} s',font=font,fill='#142a32')
board.save(out/'escenas.jpg',quality=93)
credits=sum(int(x['reported_character_cost'] or 0) for x in m['usage'])
validation={'all_passed':True,'versions':results,'subtitles':False,'music':False,'reported_character_cost_total':credits,'api_generation_calls':len(m['usage']),'source_visual_revision':'nienfos-presentacion-v4','timing':'Shared scene timing measured from real generated speech; natural voice speed unchanged.'}
(out/'validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n')
lines=['# Nienfos · Presentación con voces ElevenLabs','',f'Tres alternativas con el mismo guion y montaje. {plan["duration"]:g} segundos · 720×1280 · 30 fps. Sin subtítulos ni música. Se conservan los títulos y diagramas de la presentación.','', '| Voz | Estilo del catálogo | Video | Solo voz |','|---|---|---|---|']
for v in m['voices']:lines.append(f'| {v["name"]} | {v["style"]} | [Ver presentación]({v["slug"]}/presentacion.mp4) | [Escuchar MP3]({v["slug"]}/narracion.mp3) |')
lines+=['','![Escenas del montaje](escenas.jpg)','', 'Se amplió ligeramente la duración de algunas escenas para que cada frase termine antes del cambio de imagen, sin acelerar las voces. La voz fue sintetizada con ElevenLabs Multilingual v2; el montaje, ajuste de nivel y controles se hicieron localmente. No se generaron efectos ni música.','',f'Consumo informado por las respuestas de la API: **{credits}** en el campo `character-cost`, en {len(m["usage"])} solicitudes. Los audios se reutilizan por huella para evitar repetir la síntesis.','', 'Validación: decodificación completa del video y audio de las tres alternativas; resolución, fotogramas, sincronización por escena, ausencia de saturación digital y cero pistas de subtítulos. La transcripción local es una comprobación aproximada, no una evaluación humana de la naturalidad.','', '[Validación técnica](validation.json) · [Guion y voces](narration.json) · [Tiempos medidos](timing.json) · [Versión anterior sin audio](../nienfos-presentacion-v4/presentacion.mp4)']
(out/'README.md').write_text('\n'.join(lines)+'\n')
