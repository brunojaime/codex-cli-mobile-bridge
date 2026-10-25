"""Deterministic focus/click cues over a real recorded tutorial; no model calls."""
from pathlib import Path
import argparse, hashlib, json, math, shutil, subprocess, time
import av
from PIL import Image,ImageDraw,ImageFont
from bookends import FF,sha
FONT='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'

def validate(plan,source):
    meta=json.loads((source/'render.json').read_text())
    if plan.get('version')!=1 or plan.get('source_sha256')!=sha(source/'rd-documentos-completo.mp4'):
        raise ValueError('Action plan does not match source video')
    events=plan.get('actions');ids=set();previous=0
    if not isinstance(events,list) or not events:raise ValueError('Actions required')
    for e in events:
        if set(e)!={'id','cue_id','start','end','pulse_at','rect','label','kind'}:raise ValueError('Invalid action fields')
        if e['id'] in ids:raise ValueError('Duplicate action');
        ids.add(e['id'])
        if not all(isinstance(e[k],(int,float)) and not isinstance(e[k],bool) and math.isfinite(e[k]) for k in ['start','end','pulse_at']):raise ValueError('Invalid times')
        if not meta['body_start']<=e['start']<e['end']<=meta['body_start']+meta['body_seconds'] or e['start']<previous:raise ValueError('Invalid or overlapping action interval')
        previous=e['end']
        if not e['start']<=e['pulse_at']<=e['end'] or e['end']-e['start']>2:raise ValueError('Invalid pulse or excessive focus duration')
        if e['cue_id'] not in {c['id'] for c in meta['cues']} or e['kind'] not in ['tap','focus','status']:raise ValueError('Unknown recorded action')
        cue=next(c for c in meta['cues'] if c['id']==e['cue_id'])
        if abs(e['pulse_at']-cue['video_seconds'])>.5:raise ValueError('Focus detached from recorded action')
        if not isinstance(e['label'],str) or not 1<=len(e['label'])<=24:raise ValueError('Invalid label')
        rect=e['rect']
        if len(rect)!=4 or not all(isinstance(x,int) and not isinstance(x,bool) for x in rect):raise ValueError('Invalid rectangle')
        x,y,w,h=rect
        if w<20 or h<20 or not (68<=x<x+w<=652 and 99<=y<y+h<=1077):raise ValueError('Rectangle outside UI')
    return plan

def annotate(im,t,events):
    e=next((e for e in events if e['start']<=t<e['end']),None)
    if e is None:return im
    alpha=int(230*min(1,(t-e['start'])/.10,(e['end']-t)/.08))
    overlay=Image.new('RGBA',im.size);d=ImageDraw.Draw(overlay);x,y,w,h=e['rect']
    if e['kind']!='status':
        d.rounded_rectangle((x,y,x+w,y+h),radius=9,outline=(0,110,155,alpha),width=4)
        d.rounded_rectangle((x-2,y-2,x+w+2,y+h+2),radius=10,outline=(255,255,255,int(alpha*.7)),width=2)
    if e['kind']=='tap':
        dt=t-e['pulse_at']
        if -.14<=dt<=.2:
            radius=12+20*(dt+.14)/.34;cx=x+min(42,w/2);cy=y+h/2
            d.ellipse((cx-radius,cy-radius,cx+radius,cy+radius),fill=(0,154,195,int(alpha*.18)),outline=(0,139,185,alpha),width=4)
    # Short action hint in the header; never covers the UI or captions.
    f=ImageFont.truetype(FONT,17);width=int(d.textlength(e['label'],font=f))+20
    d.rounded_rectangle((700-width,12,700,38),radius=7,fill=(22,72,92,alpha))
    d.text((710-width,15),e['label'],font=f,fill=(225,249,253,alpha))
    return Image.alpha_composite(im.convert('RGBA'),overlay).convert('RGB')

def render(source,out,plan_path):
    source=Path(source).resolve();out=Path(out).resolve();plan=validate(json.loads(Path(plan_path).read_text()),source)
    if out==source:raise ValueError('Do not overwrite source')
    started=time.perf_counter();out.mkdir(parents=True,exist_ok=True)
    tmp=out/'focused-silent.mp4';count=0
    with av.open(str(source/'rd-documentos-completo.mp4')) as incoming,av.open(str(tmp),'w') as target:
        stream=target.add_stream('libx264',rate=30);stream.width=720;stream.height=1280;stream.pix_fmt='yuv420p';stream.options={'crf':'18','preset':'veryfast'}
        for frame in incoming.decode(video=0):
            result=av.VideoFrame.from_image(annotate(frame.to_image(),float(frame.time),plan['actions']));result.pts=count
            for packet in stream.encode(result):target.mux(packet)
            count+=1
        for packet in stream.encode():target.mux(packet)
    subprocess.run([FF,'-v','error','-y','-i',str(tmp),'-i',str(source/'rd-documentos-completo.mp4'),'-map','0:v','-map','1:a','-c','copy','-movflags','+faststart',str(out/'rd-documentos-completo.mp4')],check=True)
    tmp.unlink()
    for name in ['narracion.wav','subtitulos.srt','portada.jpg','intro.png','outro.png']:
        shutil.copyfile(source/name,out/name)
    meta=json.loads((source/'render.json').read_text());meta['video_sha256']=sha(out/'rd-documentos-completo.mp4');meta['actions_plan']=plan
    (out/'render.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
    info={'frames':count,'duration':count/30,'actions':len(plan['actions']),'source_sha256':plan['source_sha256'],'video_sha256':meta['video_sha256'],'model_api_calls':0,'tts_calls':0,'seconds':time.perf_counter()-started}
    (out/'actions.json').write_text(json.dumps(info,indent=2)+'\n');print(json.dumps(info))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--plan',type=Path,required=True);a=p.parse_args();render(a.source,a.output,a.plan)
