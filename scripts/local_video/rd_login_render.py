"""Local login tutorial using explicit editorial timing and actual captured UI frames."""
from pathlib import Path
import argparse,bisect,json,math
import av
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from bookends import ROOT,SR,read_pcm,write_pcm,command,card,sha,stamp
from screen_template import compose,validate as validate_screen,caption_rows,FONT
from rd_full_render import compact
from guide_qc import audio_checks

FOLDER=ROOT/'reports/rd-ingreso-20260930'
def brief(folder):
    rows=[]
    for r in json.loads((folder/'voice-recipe.json').read_text())['scenes']:
        voice=read_pcm(folder/'audio'/f"{r['id']}.wav")
        item={**r,'voice_seconds':len(voice)/SR,'longest_silence':audio_checks(voice)['longest_silence_seconds']}
        p=folder/'capture'/r['id']/'frames.json'
        if p.exists():
            cap=json.loads(p.read_text());item.update(moving_seconds=compact(cap)[1],actions=cap['events'])
        rows.append(item)
    return {'version':1,'scenes':rows}

def paced_voice(folder,e):
    voice=read_pcm(folder/'audio'/f"{e['id']}.wav");chunks=[];last=0
    for pause in e.get('pauses',[]):
        point=round(pause['after_seconds']*SR);seconds=pause['seconds']
        if not last<point<len(voice) or not .1<=seconds<=1.5:raise ValueError('Invalid internal pause')
        window=voice[max(0,point-480):point+480].astype(float)/32768
        if np.sqrt(np.mean(window*window))>.018:raise ValueError('Pause must fall in measured low-energy boundary')
        chunks.extend([voice[last:point],np.zeros(round(seconds*SR),dtype='<i2')]);last=point
    chunks.append(voice[last:]);return np.concatenate(chunks)

def validate(plan,folder):
    recipe=json.loads((folder/'voice-recipe.json').read_text())['scenes']
    if plan['version']!=1 or [e['id'] for e in plan['scenes']]!=[r['id'] for r in recipe]:raise ValueError('All scenes required in order')
    if sum(e['frames'] for e in plan['scenes'])>1800:raise ValueError('Maximum 60 seconds')
    for e in plan['scenes']:
        if type(e['frames'])!=int or not 75<=e['frames']<=360:raise ValueError('Invalid duration')
        lead=e['speech_lead'];voice=paced_voice(folder,e)
        if not .15<=lead<=1 or lead+len(voice)/SR+.15>e['frames']/30:raise ValueError('Voice must fit naturally')
        if not e['reason']:raise ValueError('Editorial justification required')
    return recipe

def render(folder,output,plan_path):
    plan=json.loads(plan_path.read_text());recipe=validate(plan,folder);output.mkdir(parents=True,exist_ok=True)
    screen=json.loads((Path(__file__).parent/'skill/local-feature-videos/default-screen-template.json').read_text());screen['client']='RD · Acceso'
    rect=validate_screen(screen,[0,0,430,720])
    cfg=json.loads((ROOT/'reports/rd-video-pantalla-grande-20260929/final/render.json').read_text())['config']
    cfg={**cfg,'title':'Cómo ingresar a RD','subtitle':'Dos formas de acceso','cta':'Ingresá con tu cuenta'}
    intro=card(cfg,'intro');outro=card(cfg,'outro');intro.save(output/'portada.jpg');intro.save(output/'intro.png');outro.save(output/'outro.png')
    n=0;total=sum(e['frames'] for e in plan['scenes']);dry=np.zeros(total*1600,dtype='<i2');captions=[];timeline=[]
    with av.open(str(output/'silent.mp4'),'w') as c:
        stream=c.add_stream('libx264',rate=30);stream.width=720;stream.height=1280;stream.pix_fmt='yuv420p';stream.options={'crf':'18','preset':'veryfast','threads':'2'}
        def emit(im):
            nonlocal n
            frame=av.VideoFrame.from_image(im);frame.pts=n
            for packet in stream.encode(frame):c.mux(packet)
            n+=1
        for r,e in zip(recipe,plan['scenes']):
            start=n/30;dur=e['frames']/30;voice=paced_voice(folder,e);x=voice.astype(float)/32768
            gain=min(.10/max(np.sqrt(np.mean(x*x)),1e-6),.85/max(np.max(np.abs(x)),1e-6));offset=n*1600+round(e['speech_lead']*SR)
            dry[offset:offset+len(voice)]=np.round(voice*gain).astype('<i2')
            text=r['display_text'];caption_rows(text,ImageFont.truetype(FONT,screen['caption_font']),684)
            local_captions=[(.05,dur-.05,text)];captions.append((start+.05,start+dur-.05,text))
            entry={**e,'start':start,'end':start+dur,'voice_start':offset/SR,'voice_end':(offset+len(voice))/SR,'gain':gain,'voice_sha256':sha(folder/'audio'/f"{e['id']}.wav"),'actions':[]}
            if e['id'] in ('intro','outro'):
                im=(intro if e['id']=='intro' else outro).copy()
                d=ImageDraw.Draw(im);font=ImageFont.truetype(FONT,27)
                for i,line in enumerate(caption_rows(text,font,684)):
                    w=d.textlength(line,font=font);d.text(((720-w)/2,1185+i*33),line,font=font,fill='#17334b')
                for _ in range(e['frames']):emit(im)
            else:
                screen['client']='Zoho · Vista pública' if e['id']=='zoho-login' else 'RD · Acceso'
                directory=folder/'capture'/e['id'];cap=json.loads((directory/'frames.json').read_text());times,capdur=compact(cap)
                # Retain all captured visual changes, with gentle motion and final reading time.
                motion=dur-.35;factor=motion/capdur
                if 1/factor>1.3:raise ValueError('Capture too long for scene: '+e['id'])
                stamps=[f['timestamp'] for f in cap['frames']]
                for event in cap['events']:
                    idx=max(0,min(len(times)-1,bisect.bisect_right(stamps,event['timestamp'])-1));entry['actions'].append({'id':event['id'],'video_seconds':start+times[idx]*factor})
                last=-1
                for k in range(e['frames']):
                    t=k/30;idx=max(0,min(len(times)-1,bisect.bisect_right(times,t/factor)-1))
                    if idx!=last:
                        with Image.open(directory/cap['frames'][idx]['file']) as raw:im=raw.convert('RGB')
                        last=idx
                    emit(compose(im,t,{'body_start':0,'body_seconds':dur},screen,[0,0,430,720],rect,local_captions))
                entry.update(capture_sha256=sha(directory/'frames.json'),capture_seconds=capdur,motion_seconds=motion)
            timeline.append(entry);print(e['id'],round(start,2),dur,flush=True)
        for packet in stream.encode():c.mux(packet)
    write_pcm(output/'narracion.wav',dry)
    command(['-i',output/'silent.mp4','-i',output/'narracion.wav','-map','0:v','-map','1:a','-c:v','copy','-c:a','aac','-b:a','128k','-movflags','+faststart',output/'rd-documentos-completo.mp4'])
    (output/'silent.mp4').unlink()
    (output/'subtitulos.srt').write_text('\n\n'.join(f'{i+1}\n{stamp(a)} --> {stamp(b)}\n{text}' for i,(a,b,text) in enumerate(captions))+'\n')
    meta={'duration':n/30,'frames':n,'voice':'voz-1','model_api_calls':0,'screen_template':screen,'ui_rect':rect,'config':cfg,'timeline':timeline,'plan_sha256':sha(plan_path),'video_sha256':sha(output/'rd-documentos-completo.mp4')}
    (output/'render.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n');return meta
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--folder',type=Path,default=FOLDER);p.add_argument('--output',type=Path);p.add_argument('--plan',type=Path);p.add_argument('--brief',action='store_true');a=p.parse_args()
    if a.brief:print(json.dumps(brief(a.folder),ensure_ascii=False,separators=(',',':')))
    else:render(a.folder,a.output,a.plan)
