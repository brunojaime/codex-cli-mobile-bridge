"""Reusable offline opening/closing. Stream-copy the approved tutorial; encode audio once."""
from pathlib import Path
import argparse, hashlib, json, math, re, subprocess, sys, time, wave
import av
import numpy as np
from scipy.signal import resample_poly
from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg

ROOT=Path(__file__).resolve().parents[2]
FF=imageio_ffmpeg.get_ffmpeg_exe()
FONT='/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf'
BOLD='/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf'
FPS=30; SR=48000

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def command(args): subprocess.run([FF,'-y','-v','error',*map(str,args)],check=True)
def read_pcm(p):
    with wave.open(str(p)) as f:
        assert f.getnchannels()==1 and f.getsampwidth()==2
        rate=f.getframerate(); samples=np.frombuffer(f.readframes(f.getnframes()),dtype='<i2')
    if rate!=SR: samples=np.clip(np.round(resample_poly(samples.astype(float),SR//math.gcd(SR,rate),rate//math.gcd(SR,rate))),-32768,32767).astype('<i2')
    return samples

def write_pcm(p,x):
    with wave.open(str(p),'wb') as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(SR);f.writeframes(x.astype('<i2').tobytes())

def wrapped(draw,text,size,width=576):
    font=ImageFont.truetype(BOLD,size);rows=[];row=''
    for word in text.split():
        candidate=(row+' '+word).strip()
        if draw.textlength(candidate,font=font)>width and row: rows.append(row);row=word
        else: row=candidate
    return rows+[row],font

def textblock(draw,text,y,size=52,fill='#1B3038',max_rows=3):
    floor=min(18,size)
    while size>=floor:
        rows,font=wrapped(draw,text,size)
        if len(rows)<=max_rows:break
        size-=2
    if len(rows)>max_rows:raise ValueError('Text too long for the card')
    for row in rows:draw.text((72,y),row,font=font,fill=fill);y+=int(size*1.38)
    return y

def card(cfg,kind):
    im=Image.new('RGB',(720,1280),'#F4F6F5');d=ImageDraw.Draw(im)
    d.line((72,302,124,302),fill='#7F9EA7',width=4)
    textblock(d,cfg['client'] if kind=='intro' else 'ASÍ DE SIMPLE',334,19,max_rows=2)
    if kind=='intro':
        y=textblock(d,cfg['title'],408,57)
        textblock(d,cfg['subtitle'],y+30,25,fill='#5B6A70')
        d.line((72,856,648,856),fill='#DCE2E1',width=2)
        textblock(d,'GUÍA RÁPIDA',882,18,fill='#5B6A70')
    else:
        textblock(d,cfg['cta'],410,53)
        textblock(d,cfg['closing_label'],738,18,fill='#5B6A70',max_rows=2)
        d.line((72,796,648,796),fill='#DCE2E1',width=2)
        for key,x in [('studio_logo',72),('client_logo',399)]:
            logo=Image.open(ROOT/cfg[key]).convert('RGBA')
            # Crop transparent padding only; keep all colored pixels and proportions.
            box=logo.getbbox()
            if box:logo=logo.crop(box)
            logo.thumbnail((249,104),Image.Resampling.LANCZOS)
            im.paste(logo,(x+(249-logo.width)//2,845+(104-logo.height)//2),logo)
        d.line((360,852,360,943),fill='#DCE2E1',width=2)
    return im

def stamp(t):
    ms=round(t*1000);return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
def seconds(s):
    h,m,rest=s.replace(',','.').split(':');return int(h)*3600+int(m)*60+float(rest)

def render(config,output):
    started=time.perf_counter();cfg=json.loads(Path(config).read_text());out=Path(output).resolve();body=(ROOT/cfg['body']).resolve()
    with av.open(str(body/'rd-documentos.mp4')) as c:
        v=c.streams.video[0];body_frames=v.frames;body_seconds=float(v.duration*v.time_base)
        assert (v.width,v.height,float(v.average_rate))==(720,1280,30)
    cap=min(60,float(cfg['maximum_seconds'])); minimum=float(cfg['minimum_card_seconds'])
    if minimum<1 or body_seconds+2*minimum>cap:raise ValueError('Opening + body + closing exceeds maximum 60 seconds')
    out.mkdir(parents=True,exist_ok=True)
    recipe={'scenes':[{'id':k,'title':k,'text':cfg[k+'_speech']} for k in ('intro','outro')]}
    (out/'bookends-speech.json').write_text(json.dumps(recipe,ensure_ascii=False,indent=2)+'\n')
    subprocess.run([sys.executable,str(ROOT/'scripts/local_video/voice.py'),str(out/'bookends-speech.json'),'--output',str(out/'audio')],check=True)
    speech={k:read_pcm(out/'audio'/f'{k}.wav') for k in ('intro','outro')}
    lead=float(cfg['speech_lead_seconds']);tail=float(cfg['speech_tail_seconds'])
    if lead<0 or tail<0:raise ValueError('Negative speech padding')
    frames={k:math.ceil(max(minimum,lead+len(speech[k])/SR+tail)*FPS) for k in speech}
    total=(frames['intro']+body_frames+frames['outro'])/FPS
    if total>cap:raise ValueError('Narration exceeds maximum 60 seconds; shorten the bookend text')
    edit=out/'edit';edit.mkdir(exist_ok=True)
    for k in speech:
        card(cfg,k).save(out/f'{k}.png')
        dur=frames[k]/FPS
        command(['-loop','1','-framerate',FPS,'-i',out/f'{k}.png','-vf',('format=yuv420p' if k=='intro' and cfg.get('instant_intro',False) else 'fade=t=in:st=0:d=0.25:color=0xF4F6F5,format=yuv420p'),'-frames:v',frames[k],'-an','-c:v','libx264','-preset','veryfast','-crf','20','-threads','2',edit/f'{k}.mp4'])
    command(['-i',body/'rd-documentos.mp4','-map','0:v:0','-c:v','copy','-an',edit/'body.mp4'])
    (edit/'concat.txt').write_text("file 'intro.mp4'\nfile 'body.mp4'\nfile 'outro.mp4'\n")
    command(['-f','concat','-safe','0','-i',edit/'concat.txt','-map','0:v:0','-c:v','copy',edit/'video.mp4'])
    full=np.zeros(round(total*SR),dtype='<i2');start=frames['intro']*1600
    approved=read_pcm(body/'aligned-narration.wav');assert len(approved)<=body_frames*1600
    full[start:start+len(approved)]=approved
    offsets={'intro':round(lead*SR),'outro':start+body_frames*1600+round(lead*SR)}
    gains={}
    for k,wav in speech.items():
        gain=min(1.5,23000/max(1,int(np.abs(wav.astype(float)).max())));gains[k]=gain
        full[offsets[k]:offsets[k]+len(wav)]=np.round(wav*gain).astype('<i2')
    write_pcm(out/'narracion.wav',full)
    command(['-i',edit/'video.mp4','-i',out/'narracion.wav','-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','128k','-movflags','+faststart',out/'rd-documentos-completo.mp4'])
    command(['-i',out/'narracion.wav','-c:a','libmp3lame','-b:a','128k',out/'narracion.mp3'])
    blocks=[(lead,lead+len(speech['intro'])/SR,cfg['intro_speech'])]
    for block in (body/'subtitulos.srt').read_text().strip().split('\n\n'):
        lines=block.splitlines();a,b=lines[1].split(' --> ');blocks.append((seconds(a)+start/SR,seconds(b)+start/SR,'\n'.join(lines[2:])))
    blocks.append((offsets['outro']/SR,(offsets['outro']+len(speech['outro']))/SR,cfg['outro_speech']))
    (out/'subtitulos.srt').write_text('\n\n'.join(f'{i+1}\n{stamp(a)} --> {stamp(b)}\n{t}' for i,(a,b,t) in enumerate(blocks))+'\n')
    old=json.loads((body/'render.json').read_text())
    result={'duration':total,'body_seconds':body_seconds,'body_start':start/SR,'intro_frames':frames['intro'],'body_frames':body_frames,'outro_frames':frames['outro'],'fps':FPS,'sample_rate':SR,'voice':'voz-1','audio_offsets_samples':offsets,'audio_gains':gains,'body_sha256':sha(body/'rd-documentos.mp4'),'body_pcm_sha256':sha(body/'aligned-narration.wav'),'video_sha256':sha(out/'rd-documentos-completo.mp4'),'config':cfg,'render_seconds':time.perf_counter()-started,'model_api_integration':'none','cues':[{**c,'video_seconds':c['video_seconds']+start/SR} for c in old['cues']]}
    (out/'render.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'seconds':total,'render_seconds':result['render_seconds']}))
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,default=ROOT/'scripts/local_video/rd-bookends.json');p.add_argument('--output',type=Path,required=True);a=p.parse_args();render(a.config,a.output)
