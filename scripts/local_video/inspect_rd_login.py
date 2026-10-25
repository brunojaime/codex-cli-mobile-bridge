"""Decode final login MP4 and prepare frames for an actual visual observer."""
from pathlib import Path
import json
import av,numpy as np
from PIL import Image,ImageDraw,ImageFont
from bookends import sha,read_pcm,SR
from rd_login_render import FOLDER
from guide_qc import inspect,audio_checks
p=FOLDER;movie=p/'final/rd-documentos-completo.mp4';meta=json.loads((p/'final/render.json').read_text())
points=[('portada',0)]
for s in meta['timeline']:
    if s['id']!='intro':
        points.append((s['id'],round((s['end']-.5)*30)))
        if s['id'] in ('reset','app-login'):points.append((s['id']+'-form',round((s['start']+(s['end']-s['start'])*.65)*30)))
frames=p/'frames';frames.mkdir(exist_ok=True);targets={i:name for name,i in points};rows=[]
with av.open(str(movie)) as c:
    for i,f in enumerate(c.decode(video=0)):
        if i in targets:
            file='frames/'+targets[i]+'.jpg';f.to_image().save(p/file,quality=95);rows.append({'id':targets[i],'time':i/30,'path':file})
assert len(rows)==len(points)
sheet=Image.new('RGB',(1200,558*((len(rows)+3)//4)),'#e8eef3');d=ImageDraw.Draw(sheet);font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',13)
for i,r in enumerate(rows):
    im=Image.open(p/r['path']);im.thumbnail((300,533));x=i%4*300;y=i//4*558;sheet.paste(im,(x,y+25));d.text((x+4,y+4),f"{r['time']:.1f}s · {r['id']}",font=font,fill='#102b43')
sheet.save(p/'fotogramas.jpg',quality=95)
qc=inspect(p/'final')
with av.open(str(movie)) as c:
    a=c.streams.audio[0];duration=float(a.duration*a.time_base);audio=np.concatenate([f.to_ndarray().reshape(-1) for f in c.decode(audio=0)])
qc.update(decoded_audio_duration=duration,decoded_audio_peak=float(np.max(np.abs(audio))),frames_for_visual_review=rows,visual_observer_pending=True)
assert abs(duration-meta['duration'])<.03 and qc['decoded_audio_peak']<1
# Local approximate word timestamps validate the three field/save transitions.
alignment=json.loads((p/'alignment.json').read_text());scene=next(s for s in meta['timeline'] if s['id']=='reset');spoken=next(s for s in alignment['scenes'] if s['id']=='reset')
import unicodedata,re
norm=lambda t:re.sub('[^a-z]','',unicodedata.normalize('NFKD',t.lower()))
sync=[]
for word,event in [('elegi','new-password-field'),('repetila','repeat-password-field'),('guarda','save-password')]:
    w=next(w for w in spoken['words'] if norm(w['word'])==word)
    voice_time=scene['voice_start']+w['start']+sum(x['seconds'] for x in scene['pauses'] if x['after_seconds']<=w['start'])
    action_time=next(a['video_seconds'] for a in scene['actions'] if a['id']==event)
    sync.append({'word':word,'action':event,'voice_seconds':voice_time,'action_seconds':action_time,'delta_seconds':abs(voice_time-action_time)})
assert all(s['delta_seconds']<.85 for s in sync),sync
qc['reset_word_action_alignment']=sync
(p/'media-qc.json').write_text(json.dumps(qc,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in qc.items() if k!='frames_for_visual_review'}))
