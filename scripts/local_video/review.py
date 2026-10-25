"""Contact sheets from the exported video for an actual visual observer."""
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
import argparse,av,json
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);out=p.parse_args().output
meta=json.loads((out/'render.json').read_text());times=[c['video_seconds']+.08 for c in meta['cues']]
sequence=[6.7+i*.22 for i in range(8)]
wanted=[('cue',i,t) for i,t in enumerate(times)]+[('motion',i,t) for i,t in enumerate(sequence)]
frames={};c=av.open(str(out/'rd-documentos.mp4'))
for f in c.decode(video=0):
 t=float(f.pts*f.time_base)
 for kind,i,target in wanted:
  if (kind,i) not in frames and t>=target:frames[kind,i]=f.to_image()
 if len(frames)==len(wanted):break
for kind,count,cols in [('cue',9,3),('motion',8,4)]:
 sheet=Image.new('RGB',(cols*240,((count+cols-1)//cols)*450),'#102b43');d=ImageDraw.Draw(sheet)
 for i in range(count):
  x=(i%cols)*240;y=(i//cols)*450;sheet.paste(frames[kind,i].resize((240,427)),(x,y+23))
  label=f"{meta['cues'][i]['id']} · {times[i]:.2f}s" if kind=='cue' else f'{sequence[i]:.2f}s'
  d.text((x+8,y+4),label,fill='white',font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',13))
 sheet.save(out/f'{kind}-review.jpg',quality=92)
