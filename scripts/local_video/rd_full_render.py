"""Offline three-chapter RD tutorial. Explicit plan; real captured frames; cached narration."""
from pathlib import Path
import argparse, bisect, json, math, shutil
import av
import numpy as np
from PIL import Image
from bookends import ROOT, SR, read_pcm, write_pcm, command, card, sha, stamp
from screen_template import compose, validate as validate_screen, subtitles
from guide_qc import audio_checks

DEFAULT_SOURCE=ROOT/'reports/rd-video-pantalla-grande-20260929/final'
RECIPE=Path(__file__).with_name('rd-full-tutorial.json')

def compact(capture):
    """Remove only long unchanged capture waits, keeping every recorded visual change."""
    times=[0.]
    for a,b in zip(capture['frames'],capture['frames'][1:]):
        times.append(times[-1]+min(.6,max(0,b['timestamp']-a['timestamp'])))
    return times,times[-1]+.6

def brief(folder):
    rows=[]
    for scene in json.loads(RECIPE.read_text())['scenes']:
        wav=folder/'audio'/f"{scene['id']}.wav"
        cap=folder/'capture'/scene['id']/'frames.json'
        row={**scene,'voice_seconds':round(len(read_pcm(wav))/SR,3) if wav.exists() else None}
        if wav.exists():row['voice_longest_silence_seconds']=audio_checks(read_pcm(wav))['longest_silence_seconds']
        if cap.exists():
            c=json.loads(cap.read_text());times,duration=compact(c)
            row.update(capture_seconds=round(c['duration'],3),moving_seconds=round(duration,3),actions=[e['id'] for e in c['events']])
        rows.append(row)
    return {'version':1,'scenes':rows,'existing_body_seconds':32.9666666667,'existing_closing_seconds':3.5}

def validate(plan,folder):
    recipe=json.loads(RECIPE.read_text())['scenes']
    if plan.get('version')!=1 or plan.get('long_form_authorized_by')!='source-d9f5636e80fdc9791b88c69d':
        raise ValueError('Long-form authorization and schema required')
    if [s['id'] for s in plan['scenes']]!=[s['id'] for s in recipe]:raise ValueError('All scenes required in order')
    for entry in plan['scenes']:
        if type(entry['frames']) is not int or not 90<=entry['frames']<=450:raise ValueError('Scene duration invalid')
        lead=entry['speech_lead'];dur=entry['frames']/30
        if not isinstance(lead,(int,float)) or not math.isfinite(lead) or not 0.15<=lead<=2:raise ValueError('Speech lead invalid')
        speech=len(read_pcm(folder/'audio'/f"{entry['id']}.wav"))/SR
        if lead+speech+.25>dur:raise ValueError('Voice does not fit: '+entry['id'])
        if not entry.get('reason'):raise ValueError('Editorial reason required')
        cap=folder/'capture'/entry['id']/'frames.json'
        if cap.exists() and compact(json.loads(cap.read_text()))[1]/dur>1.3:raise ValueError('Capture movement too fast')
    total=sum(s['frames'] for s in plan['scenes'])/30+1094/30
    if not 60<total<300:raise ValueError('Expected explicitly authorized extended tutorial under five minutes')
    return recipe

def render(folder,output,plan_path):
    plan=json.loads(plan_path.read_text());recipe=validate(plan,folder);output.mkdir(parents=True,exist_ok=True)
    approved=DEFAULT_SOURCE;old=json.loads((approved/'render.json').read_text())
    screen=json.loads((Path(__file__).parent/'skill/local-feature-videos/default-screen-template.json').read_text());screen['client']='RD'
    rect=validate_screen(screen,[0,0,430,720])
    cfg=dict(old['config']);cfg.update(title='Firma, plantillas y novedades',subtitle='Configuración y uso, paso a paso')
    intro=card(cfg,'intro');intro.save(output/'intro.png');intro.save(output/'portada.jpg')
    cfg.update(title='Cargar una novedad',subtitle='Otro ejemplo: documento, vigencia y correo')
    chapter=card(cfg,'intro')
    counts=sum(e['frames'] for e in plan['scenes']);old_start=round(old['body_start']*30)
    with av.open(str(approved/'rd-documentos-completo.mp4')) as c:old_frames=c.streams.video[0].frames
    total_frames=counts+old_frames-old_start
    dry=np.zeros(total_frames*1600,dtype='<i2');caption=[];timeline=[];n=0
    silent=output/'silent.mp4'
    with av.open(str(silent),'w') as container:
        stream=container.add_stream('libx264',rate=30);stream.width=720;stream.height=1280;stream.pix_fmt='yuv420p';stream.options={'crf':'18','preset':'veryfast','threads':'2'}
        def emit(im):
            nonlocal n
            frame=av.VideoFrame.from_image(im);frame.pts=n
            for p in stream.encode(frame):container.mux(p)
            n+=1
        for r,e in zip(recipe,plan['scenes']):
            start=n/30;duration=e['frames']/30;voice=read_pcm(folder/'audio'/f"{e['id']}.wav")
            # Same natural timing; only gain normalization, never time stretching or pitch shifting.
            x=voice.astype(float)/32768;rms=np.sqrt(np.mean(x*x));peak=np.max(np.abs(x));gain=min(.10/max(rms,1e-6),.85/max(peak,1e-6))
            offset=n*1600+round(e['speech_lead']*SR);dry[offset:offset+len(voice)]=np.round(voice*gain).astype('<i2')
            capstart=start+.15;capend=start+duration-.1;caption.append((capstart,capend,r['text']))
            entry={**e,'start':start,'end':start+duration,'voice_start':offset/SR,'voice_end':(offset+len(voice))/SR,'gain':gain,'voice_sha256':sha(folder/'audio'/f"{e['id']}.wav"),'actions':[]}
            if e['id'] in ('intro','documents-chapter'):
                im=intro if e['id']=='intro' else chapter
                for _ in range(e['frames']):emit(im)
            else:
                directory=folder/'capture'/e['id'];capture=json.loads((directory/'frames.json').read_text());times,capdur=compact(capture)
                # Leave a readable final state; moving frames keep their original ordering.
                motion_duration=min(duration-.7,max(capdur/1.15,duration-1.4));factor=motion_duration/capdur
                stamps=[f['timestamp'] for f in capture['frames']]
                for event in capture['events']:
                    idx=max(0,min(len(times)-1,bisect.bisect_right(stamps,event['timestamp'])-1))
                    entry['actions'].append({'id':event['id'],'source_timestamp':event['timestamp'],'video_seconds':start+times[idx]*factor})
                screen['client']='RD · Firma' if e['id'].startswith('signature') else 'RD · Plantillas'
                last_idx=-1;im=None
                for k in range(e['frames']):
                    t=k/30;idx=max(0,min(len(times)-1,bisect.bisect_right(times,t/factor)-1))
                    if idx!=last_idx:
                        with Image.open(directory/capture['frames'][idx]['file']) as raw:im=raw.convert('RGB')
                        last_idx=idx
                    final=compose(im,t,{'body_start':0,'body_seconds':duration},screen,[0,0,430,720],rect,[(.15,duration-.1,r['text'])])
                    emit(final)
                entry['capture_sha256']=sha(directory/'frames.json');entry['capture_seconds']=capdur;entry['motion_seconds']=motion_duration
            timeline.append(entry)
            print(e['id'],round(start,2),round(duration,2),flush=True)
        # Reuse the entire approved novelty walkthrough and closing, decoding actual frames.
        with av.open(str(approved/'rd-documentos-completo.mp4')) as old_video:
            for i,f in enumerate(old_video.decode(video=0)):
                if i>=old_start:emit(f.to_image())
        for packet in stream.encode():container.mux(packet)
    assert n==total_frames
    original_dry=read_pcm(approved/'narracion.wav')[old_start*1600:]
    dry[counts*1600:counts*1600+len(original_dry)]=original_dry
    for a,b,text in subtitles(approved/'subtitulos.srt'):
        if a>=old['body_start']:caption.append((a-old['body_start']+counts/30,b-old['body_start']+counts/30,text))
    write_pcm(output/'narracion.wav',dry)
    command(['-i',silent,'-i',output/'narracion.wav','-map','0:v','-map','1:a','-c:v','copy','-c:a','aac','-b:a','128k','-movflags','+faststart',output/'rd-documentos-completo.mp4'])
    silent.unlink()
    (output/'subtitulos.srt').write_text('\n\n'.join(f'{i+1}\n{stamp(a)} --> {stamp(b)}\n{text}' for i,(a,b,text) in enumerate(caption))+'\n')
    shutil.copyfile(approved/'outro.png',output/'outro.png')
    meta={'duration':n/30,'frames':n,'voice':'voz-1','model_api_calls':0,'source_recipe':str(RECIPE.relative_to(ROOT)),'screen_template':screen,'ui_rect':rect,'timeline':timeline,'old_body_start':counts/30,'old_source_start':old['body_start'],'old_source_sha256':sha(approved/'rd-documentos-completo.mp4'),'old_pcm_sha256':sha(approved/'narracion.wav'),'plan_sha256':sha(plan_path),'chapters':{'Firma':timeline[1]['start'],'Plantillas':next(e['start'] for e in timeline if e['id']=='templates-open'),'Novedades':timeline[-1]['start']},'video_sha256':sha(output/'rd-documentos-completo.mp4')}
    (output/'render.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
    return meta

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--folder',type=Path,required=True);p.add_argument('--output',type=Path);p.add_argument('--plan',type=Path);p.add_argument('--brief',action='store_true');a=p.parse_args()
    if a.brief:print(json.dumps(brief(a.folder),ensure_ascii=False,separators=(',',':')))
    else:print(json.dumps(render(a.folder,a.output,a.plan),ensure_ascii=False))
