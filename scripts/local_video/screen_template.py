"""Compact portrait composition from a declared UI rectangle; local, audio stream copy."""
import argparse
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import time

import av
from PIL import Image, ImageDraw, ImageFont
from bookends import FF, sha

FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
DEFAULT = Path(__file__).parent/'skill/local-feature-videos/default-screen-template.json'


def validate(plan, source_ui):
    required = {'version','canvas','margin','header_height','caption_height','caption_font','client','background','accent'}
    if set(plan) != required or plan['version'] != 1 or plan['canvas'] != [720,1280]:
        raise ValueError('Unsupported template schema or portrait canvas')
    for key,lo,hi in [('margin',0,24),('header_height',26,48),('caption_height',80,120),('caption_font',26,30)]:
        if type(plan[key]) is not int or not lo <= plan[key] <= hi:
            raise ValueError('Invalid '+key)
    if not isinstance(plan['client'],str) or not 1 <= len(plan['client']) <= 24:
        raise ValueError('Client label must have 1–24 characters')
    for key in ['background','accent']:
        if not isinstance(plan[key],str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',plan[key]):
            raise ValueError('Invalid color')
    if len(source_ui)!=4 or any(type(x) is not int for x in source_ui):
        raise ValueError('Source UI requires integer x, y, width, height')
    x,y,w,h=source_ui
    if min(x,y)<0 or min(w,h)<20 or x+w>720 or y+h>1280:
        raise ValueError('Source UI outside frame')
    available_w=720-2*plan['margin'];available_h=1280-plan['header_height']-plan['caption_height']
    scale=min(available_w/w,available_h/h)
    tw,th=round(w*scale),round(h*scale)
    return [(720-tw)//2,plan['header_height']+(available_h-th)//2,tw,th]


def subtitles(path):
    def seconds(value):
        h,m,s=value.replace(',','.').split(':');return int(h)*3600+int(m)*60+float(s)
    result=[]
    for block in path.read_text().strip().split('\n\n'):
        rows=block.splitlines();start,end=rows[1].split(' --> ')
        result.append((seconds(start),seconds(end),' '.join(rows[2:])))
    return result


def caption_rows(text, font, width):
    rows=[];line='';draw=ImageDraw.Draw(Image.new('RGB',(1,1)))
    for word in text.split():
        trial=(line+' '+word).strip()
        if draw.textlength(trial,font=font)>width:
            if not line:raise ValueError('Caption word too wide')
            rows.append(line);line=word
        else:line=trial
    if line:rows.append(line)
    if len(rows)>2:raise ValueError('Caption needs more than two lines; shorten or split it')
    return rows


def compose(image,t,meta,plan,source_ui,target_ui,captions):
    if not meta['body_start'] <= t < meta['body_start']+meta['body_seconds']:
        return image
    canvas=Image.new('RGB',(720,1280),plan['background']);draw=ImageDraw.Draw(canvas)
    x,y,w,h=source_ui;tx,ty,tw,th=target_ui
    canvas.paste(image.crop((x,y,x+w,y+h)).resize((tw,th),Image.Resampling.LANCZOS),(tx,ty))
    small=ImageFont.truetype(FONT,17)
    draw.text((12,4),plan['client'],font=small,fill=plan['accent'])
    note='DEMO · sin envío real';width=draw.textlength(note,font=small)
    if draw.textlength(plan['client'],font=small)+width+36>720:raise ValueError('Header labels overlap')
    draw.text((708-width,4),note,font=small,fill='white')
    cy=1280-plan['caption_height']
    progress=(t-meta['body_start'])/meta['body_seconds']
    draw.rectangle((12,cy,708,cy+1),fill='#34516a')
    draw.rectangle((12,cy,12+696*progress,cy+1),fill=plan['accent'])
    text=next((text for start,end,text in captions if start<=t<end),'')
    font=ImageFont.truetype(FONT,plan['caption_font'])
    rows=caption_rows(text,font,684)
    for index,row in enumerate(rows):
        width=draw.textlength(row,font=font)
        draw.text(((720-width)/2,cy+7+index*32),row,font=font,fill='white')
    return canvas


def render(source,output,plan_path,source_ui):
    source=Path(source).resolve();output=Path(output).resolve()
    if source==output or output in source.parents:raise ValueError('Output must not replace source')
    plan=json.loads(Path(plan_path).read_text());target_ui=validate(plan,source_ui)
    meta=json.loads((source/'render.json').read_text());captions=subtitles(source/'subtitulos.srt')
    for _,_,text in captions:caption_rows(text,ImageFont.truetype(FONT,plan['caption_font']),684)
    video=source/'rd-documentos-completo.mp4';output.mkdir(parents=True,exist_ok=True)
    temp=output/'screen-silent.mp4';started=time.perf_counter();count=0
    with av.open(str(video)) as incoming,av.open(str(temp),'w') as target:
        info=incoming.streams.video[0]
        if (info.width,info.height)!=(720,1280) or float(info.average_rate)!=30:raise ValueError('Expected portrait 720x1280 at 30 fps')
        stream=target.add_stream('libx264',rate=30);stream.width=720;stream.height=1280;stream.pix_fmt='yuv420p';stream.options={'crf':'18','preset':'veryfast','threads':'2'}
        for frame in incoming.decode(video=0):
            result=compose(frame.to_image(),float(frame.time),meta,plan,source_ui,target_ui,captions)
            encoded=av.VideoFrame.from_image(result);encoded.pts=count
            for packet in stream.encode(encoded):target.mux(packet)
            count+=1
        for packet in stream.encode():target.mux(packet)
    subprocess.run([FF,'-v','error','-y','-i',str(temp),'-i',str(video),'-map','0:v','-map','1:a','-c','copy','-movflags','+faststart',str(output/video.name)],check=True)
    temp.unlink()
    for name in ['narracion.wav','subtitulos.srt','portada.jpg','intro.png','outro.png','mezcla.wav','musica.wav','music.json','audio-con-musica.mp3']:
        if (source/name).exists():shutil.copyfile(source/name,output/name)
    meta.update(video_sha256=sha(output/video.name),screen_template=plan,ui_rect=target_ui,source_ui_rect=source_ui)
    (output/'render.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
    result={'frames':count,'duration':count/30,'source_sha256':sha(video),'video_sha256':meta['video_sha256'],'source_ui':source_ui,'target_ui':target_ui,'before_area_fraction':source_ui[2]*source_ui[3]/(720*1280),'after_area_fraction':target_ui[2]*target_ui[3]/(720*1280),'tts_calls':0,'model_api_calls':0,'audio':'stream copy','seconds':time.perf_counter()-started}
    (output/'screen-template.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--plan',type=Path,default=DEFAULT);p.add_argument('--source-ui',type=int,nargs=4,required=True);a=p.parse_args()
    render(a.source,a.output,a.plan,a.source_ui)
