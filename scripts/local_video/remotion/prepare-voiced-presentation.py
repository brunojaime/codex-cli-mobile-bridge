"""Measure real speech and align a single shared edit for all voice alternatives."""
from pathlib import Path
import json,re,subprocess,math
import numpy as np
import imageio_ffmpeg
ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
root=Path(__file__).resolve().parents[3]
p=Path(__file__).resolve().parent
out=root/'reports/videos/nienfos-presentacion-v5-voces'
m=json.loads((out/'narration.json').read_text())
rate=44100
tracks={};durations={}
for v in m['voices']:
 clips=[]
 for i in range(6):
  source=out/v['slug']/f'frase-{i+1}.mp3'
  raw=subprocess.check_output([ffmpeg,'-v','error','-i',str(source),'-ar',str(rate),'-ac','1','-f','f32le','pipe:1'])
  a=np.frombuffer(raw,dtype='<f4').copy()
  # Retain 90 ms around detected speech; remove only provider leading/trailing silence.
  active=np.flatnonzero(np.abs(a)>.003)
  assert active.size,source
  a=a[max(0,active[0]-int(.09*rate)):min(len(a),active[-1]+int(.10*rate))]
  assert np.isfinite(a).all()
  clips.append(a)
 tracks[v['slug']]=clips;durations[v['slug']]=[round(len(a)/rate,3) for a in clips]
minimum=[90,135,135,135,105,90]
frames=[max(minimum[i],math.ceil((max(d[i] for d in durations.values())+.50)*30)) for i in range(6)]
starts=[];cursor=0
for n in frames:starts.append(cursor);cursor+=n
for v in m['voices']:
 a=np.zeros(round(cursor/30*rate),dtype=np.float32)
 for i,clip in enumerate(tracks[v['slug']]):
  start=round((starts[i]/30+.18)*rate)
  a[start:start+len(clip)]+=clip
 raw=out/v['slug']/'narracion.f32';raw.write_bytes(a.astype('<f4').tobytes())
 args=[ffmpeg,'-v','error','-y','-f','f32le','-ar',str(rate),'-ac','1','-i',str(raw),'-af','loudnorm=I=-16:TP=-1.5:LRA=9','-ar',str(rate),'-c:a','pcm_s16le',str(out/v['slug']/'narracion.wav')]
 subprocess.run(args,check=True);raw.unlink()
 subprocess.run([ffmpeg,'-v','error','-y','-i',str(out/v['slug']/'narracion.wav'),'-c:a','libmp3lame','-b:a','160k',str(out/v['slug']/'narracion.mp3')],check=True)
plan={'fps':30,'frames':frames,'starts':starts,'total_frames':cursor,'duration':cursor/30,'speech_seconds':durations,'speech_inset_seconds':.18,'subtitles':False,'rationale':'Cada escena dura al menos su duración aprobada o la frase más larga más 0,50 s. No se acelera la voz.','texts':m['texts']}
(out/'timing.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
source=(p/'src/PresentationV4.tsx').read_text().replace('presentationV4Scenes','presentationV5Scenes').replace('PresentationV4','PresentationV5').replace('NienfosPresentacionV4','NienfosPresentacionV5')
i=iter(frames);source=re.sub(r'frames:\d+',lambda match:'frames:'+str(next(i)),source)
source=source.replace('durationInFrames={690}',f'durationInFrames={{{cursor}}}')
(p/'src/PresentationV5.tsx').write_text(source)
r=p/'src/Root.tsx';s=r.read_text()
if "import {PresentationV5Root}" not in s:
 s=s.replace("import {PresentationV4Root} from './PresentationV4';","import {PresentationV4Root} from './PresentationV4';\nimport {PresentationV5Root} from './PresentationV5';").replace('<PresentationV4Root/>','<PresentationV4Root/>\n  <PresentationV5Root/>');r.write_text(s)
s=(p/'render-presentation-v4.mjs').read_text().replace('nienfos-presentacion-v4','nienfos-presentacion-v5-voces').replace('NienfosPresentacionV4','NienfosPresentacionV5').replace("'presentacion.mp4'","'visual-sin-audio.mp4'").replace('/690',f'/{cursor}')
(p/'render-presentation-v5.mjs').write_text(s)
q=root/'.local-videos/nienfos-presentacion-v5-voces/request.json';d=json.loads(q.read_text());d.update(status='rendering',voice={'provider':'ElevenLabs','alternatives':[v['name'] for v in m['voices']]},music={'mode':'none'},screen_template=None,recipe='reports/videos/nienfos-presentacion-v5-voces/timing.json',subtitle_policy='none',blockers=[],render_started=True,next_steps=['Render y validación de tres versiones narradas']);q.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(plan,ensure_ascii=False))
