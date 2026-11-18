"""Check temporal variation and capture representative transition frames."""
from pathlib import Path
import json
import sys
import av
import numpy as np
from PIL import Image, ImageDraw, ImageFont
p=Path(__file__).resolve().parent
root=p.parents[2]
out=root/'reports/videos/nienfos-10-profesional'
stories=json.loads((p/'campaign-pro.json').read_text())
font=ImageFont.truetype('/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf',14)
results=[]
for s in stories:
 if sys.argv[1:] and s["id"] not in sys.argv[1:]:continue
 folder=out/s['id'];samples={};targets=set();t=0
 for shot in s['scenes']:
  targets.update([t+20,t+50]);t+=round(shot['seconds']*30)
 first_boundary=round(s['scenes'][0]['seconds']*30)
 transition=[first_boundary-3,first_boundary+4,first_boundary+9,first_boundary+16]
 targets.update(transition)
 with av.open(str(folder/'video.mp4')) as c:
  for i,frame in enumerate(c.decode(video=0)):
   if i in targets:samples[i]=frame.to_image()
 metrics=[];t=0
 for shot in s['scenes']:
  a=np.array(samples[t+20].resize((180,320))).astype(float)
  b=np.array(samples[t+50].resize((180,320))).astype(float)
  change=float(np.mean(np.abs(a-b)))
  assert change>.05,(s['id'],shot['layout'],'unexpected static shot')
  metrics.append({'layout':shot['layout'],'difference_over_one_second':round(change,3)})
  t+=round(shot['seconds']*30)
 strip=Image.new('RGB',(960,462),'#e5ebe8');draw=ImageDraw.Draw(strip)
 for j,n in enumerate(transition):
  im=samples[n];im.thumbnail((240,427));strip.paste(im,(j*240,30));draw.text((j*240+10,7),f'{n/30:.2f} s · transición',font=font,fill='#142a32')
 strip.save(folder/'transicion.jpg',quality=92)
 results.append({'id':s['id'],'all_shots_have_temporal_change':True,'scenes':metrics})
 print('MOTION '+s['id']+' verified',flush=True)
(out/('motion-validation.json' if not sys.argv[1:] else 'motion-pilot.json')).write_text(json.dumps({'results':results,'all_passed':True,'scope':'Pixel variation is evidence of movement, not a subjective quality score.'},ensure_ascii=False,indent=2)+'\n')
