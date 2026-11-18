"""Local piecewise timing: map recorded actions to words without resynthesizing voice."""
from pathlib import Path
import argparse, bisect, json, time, unicodedata, wave
import numpy as np
from scipy.signal import resample_poly
from PIL import Image, ImageDraw, ImageFont
from render import run, quoted, stamp, FONT, BOLD, ROOT
import pacing
import editorial

def normalize_text(text):
    return ''.join(c for c in unicodedata.normalize('NFD',text.lower()) if c.isalnum())

# Word indices refer to the locally inspected alignment for this fixed four-phrase recipe.
CUES={'abrir':[('open',3),('category',8)],'documento':[('upload',2),('validity',6)],
      'correo':[('recipients',2),('review',4),('template',8)],'guardar':[('save',5),('background',9)]}
CAPTIONS={'abrir':[(0,2.24,'Desde el cliente, abrí Agregar novedad'),(2.24,4.56,'y elegí la categoría del documento.')],
'documento':[(0,.98,'Cargá el archivo'),(.98,2.92,'y completá su vigencia.')],
'correo':[(0,2.50,'Elegí los destinatarios y revisá el correo.'),(3.12,5.96,'La plantilla completa los datos por vos.')],
'guardar':[(0,2.72,'Cuando esté todo listo, tocá Guardar y enviar.'),(3.06,5.56,'La carga continúa en segundo plano.')]}
LEAD=.65

def wrap(draw,text,font,width=640):
    rows=[]; row=''
    for word in text.split():
        candidate=(row+' '+word).strip()
        if draw.textlength(candidate,font=font)>width: rows.append(row);row=word
        else:row=candidate
    return rows+[row]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--calm',action='store_true');p.add_argument('--guide',action='store_true');p.add_argument('--pacing-plan',type=Path);a=p.parse_args()
    if a.guide and not a.calm:p.error('--guide requires --calm')
    if a.pacing_plan and not (a.calm and a.guide):p.error('--pacing-plan requires --calm --guide')
    plan=editorial.load_plan(a.pacing_plan,a.output) if a.pacing_plan else None
    captions=pacing.CAPTIONS if a.calm else CAPTIONS
    lead=pacing.LEAD if a.calm else LEAD
    def audio_at(sid,t): return editorial.at(plan,sid,t) if plan else (pacing.at(sid,t) if a.calm else LEAD+t)
    out=a.output.resolve(); parts=out/'edit'; parts.mkdir(exist_ok=True);started=time.perf_counter()
    recipe=json.loads((ROOT/'rd-documents.json').read_text()); narration=json.loads((out/'audio/narration.json').read_text())
    alignment={s['id']:s for s in json.loads((out/'alignment.json').read_text())['scenes']}
    assert narration['profile']=='voz-1','Reviewed V2 word cues are specific to the approved voice; re-align before using another profile'
    timeline=[]; subtitles=[]; offset=0; all_cues=[]
    for number,scene in enumerate(recipe['scenes']):
        sid=scene['id']; assert normalize_text(' '.join(c[2] for c in captions[sid]))==normalize_text(scene['text']), 'Changed script: review timing cues before rendering'
        raw=out/'capture'/sid; cap=json.loads((raw/'frames.json').read_text()); frames=cap['frames']
        base=frames[0]['timestamp']; end=frames[-1]['timestamp']-base+.4
        with wave.open(str(out/'audio'/f'{sid}.wav')) as wav: spoken=wav.getnframes()/wav.getframerate()
        scene_lead=plan['scenes'][sid]['lead_seconds'] if plan else lead
        scene_tail=plan['scenes'][sid]['tail_seconds'] if plan else (pacing.TAIL if a.calm else 1.0)
        scene_pauses=sum(p['seconds'] for p in plan['scenes'][sid]['pauses']) if plan else (sum(p for _,p in pacing.PAUSES[sid]) if a.calm else 0)
        duration=round((spoken+scene_lead+scene_tail+scene_pauses)*30)/30
        sources=[0.]; targets=[0.]; scene_cues=[]
        for event,word_index in CUES[sid]:
            mark=next(e for e in cap['events'] if e['id']==event)
            frame_index=next(i for i,f in enumerate(frames) if f['timestamp']>=mark['timestamp'])
            source=frames[frame_index]['timestamp']-base
            word=alignment[sid]['words'][word_index]; target=audio_at(sid,word['start'])
            assert source>sources[-1] and target>targets[-1]
            sources.append(source);targets.append(target)
            scene_cues.append({'id':event,'scene':sid,'source_seconds':source,'source_frame':frames[frame_index]['file'],
                'word':word['word'],'speech_seconds':word['start'],'scene_seconds':target,'video_seconds':offset+target})
        sources.append(end);targets.append(duration)
        def mapped(t):
            i=min(len(sources)-2,max(0,bisect.bisect_right(sources,t)-1))
            return targets[i]+(t-sources[i])*(targets[i+1]-targets[i])/(sources[i+1]-sources[i])
        normalized=parts/f'{sid}-frames'; normalized.mkdir(exist_ok=True)
        lines=['ffconcat version 1.0']; mapped_times=[]
        for i,frame in enumerate(frames):
            Image.open(raw/frame['file']).resize((584,978),Image.Resampling.LANCZOS).save(normalized/frame['file'],quality=94)
            t=mapped(frame['timestamp']-base);next_t=mapped(frames[i+1]['timestamp']-base) if i+1<len(frames) else duration
            lines += ['file '+quoted(normalized/frame['file']),f'duration {max(.001,next_t-t):.6f}']
            mapped_times.append(t)
        lines+=['file '+quoted(normalized/frames[-1]['file'])]
        listing=parts/f'{sid}.ffconcat';listing.write_text('\n'.join(lines)+'\n')
        card=Image.new('RGB',(720,1280),'#102b43');d=ImageDraw.Draw(card)
        d.text((34,16),'RD  /  GESTIÓN DOCUMENTAL',font=ImageFont.truetype(BOLD,18),fill='#69d4e6')
        d.text((34,46),scene['title'],font=ImageFont.truetype(BOLD,27),fill='white')
        d.rounded_rectangle((63,94,657,1083),radius=20,fill='#47708b')
        for step in range(4):d.rounded_rectangle((34+step*166,1212,184+step*166,1216),radius=2,fill='#69d4e6' if step<=number else '#34516a')
        d.text((34,1246),'DEMO · datos de ejemplo · sin envío real',font=ImageFont.truetype(FONT,19),fill='#a7c5d8')
        card.save(parts/f'{sid}.png')
        args=['-threads','1','-loop','1','-framerate','30','-t',str(duration),'-i',parts/f'{sid}.png',
              '-threads','1','-safe','0','-f','concat','-i',listing]
        filters=[f'[1:v]setsar=1,fps=30,tpad=stop_mode=clone:stop_duration=2[ui]',
                 f'[0:v][ui]overlay=68:99,trim=duration={duration}[base]']
        previous='base'
        for i,(start,finish,text) in enumerate(captions[sid]):
            caption_start=max(0,audio_at(sid,start)-.25) if a.guide else audio_at(sid,start)
            caption_end=(max(0,audio_at(sid,captions[sid][i+1][0])-.25) if i+1<len(captions[sid]) else duration) if a.guide else audio_at(sid,finish)-(.1 if a.calm and i+1<len(captions[sid]) else 0)
            caption=Image.new('RGBA',(720,140));draw=ImageDraw.Draw(caption);font=ImageFont.truetype(FONT,29)
            for row,line in enumerate(wrap(draw,text,font)):draw.text((34,18+row*39),line,font=font,fill='white')
            path=parts/f'{sid}-caption-{i}.png';caption.save(path)
            args+=['-threads','1','-loop','1','-framerate','30','-t',str(duration),'-i',path]
            label=f'caption{i}';filters.append(f"[{previous}][{2+i}:v]overlay=0:1090:enable='gte(t,{caption_start:.6f})*lt(t,{caption_end:.6f})'[{label}]");previous=label
            subtitles.append(f'{len(subtitles)+1}\n{stamp(offset+caption_start)} --> {stamp(offset+caption_end)}\n{text}\n')
        if a.guide:
            # Reveal a tiny solid strip over the existing active step; UI remains unobstructed.
            args+=['-f','lavfi','-i',f'color=c=0x34516a:s=150x4:r=30:d={duration}']
            bg_index=2+len(captions[sid]);fg_index=bg_index+1
            args+=['-f','lavfi','-i',f'color=c=0x69d4e6:s=150x4:r=30:d={duration}']
            x=34+number*166
            filters += [f'[{previous}][{bg_index}:v]overlay={x}:1212[track]', f'[{fg_index}:v]format=rgba,geq=r=105:g=212:b=230:a=255*lte(X/W\\,T/{duration})[fill]', f'[track][fill]overlay={x}:1212[progress]']
            previous='progress'
        filters += [f'[{previous}]format=yuv420p[v]']
        run(args+['-filter_complex_threads','1','-filter_complex',';'.join(filters),'-map','[v]',
                  '-t',str(duration),'-an','-c:v','libx264','-preset','veryfast','-crf','20','-threads','2','-movflags','+faststart',parts/f'{sid}.mp4'])
        timeline.append({'id':sid,'start':offset,'duration':duration,'speech_seconds':spoken,'frames_captured':len(frames),
                         'mapped_frame_times':mapped_times,'source_anchors':sources,'target_anchors':targets})
        all_cues+=scene_cues;offset+=duration
        print(sid,duration,len(frames),flush=True)
    listing=parts/'final.ffconcat';listing.write_text('ffconcat version 1.0\n'+'\n'.join('file '+quoted(parts/f'{s["id"]}.mp4') for s in recipe['scenes'])+'\n')
    # One sample-accurate PCM track, encoded once; no AAC clip priming at scene joins.
    sr=48000;track=np.zeros(round(offset*sr),dtype=np.float64);audio_segments=[]
    for scene in timeline:
        with wave.open(str(out/'audio'/f'{scene['id']}.wav')) as source:
            source_sr=source.getframerate();samples=np.frombuffer(source.readframes(source.getnframes()),dtype='<i2').astype(np.float64)/32768
        samples=resample_poly(samples,sr,source_sr)
        rms=np.sqrt(np.mean(samples*samples));peak=np.max(np.abs(samples))
        gain=min(.1/max(rms,1e-9),.85/max(peak,1e-9));samples*=gain
        intervals=editorial.intervals(plan,scene['id'],scene['speech_seconds']) if plan else (pacing.intervals(scene['id'],scene['speech_seconds']) if a.calm else [(0,scene['speech_seconds'],LEAD)])
        for chunk_index,(begin,finish,local_start) in enumerate(intervals):
            first=round(begin*sr);last=round(finish*sr);chunk=samples[first:last].copy()
            # A 4 ms fade only at inserted silence avoids clicks; speech speed is unchanged.
            fade=round(.004*sr)
            if a.calm and chunk_index: chunk[:fade]*=np.linspace(0,1,fade)
            if a.calm and chunk_index<len(intervals)-1: chunk[-fade:]*=np.linspace(1,0,fade)
            start=round((scene['start']+local_start)*sr);track[start:start+len(chunk)]=chunk
            audio_segments.append({'id':scene['id'],'chunk':chunk_index,'source_start_seconds':begin,
                'source_end_seconds':finish,'start_sample':start,'sample_count':len(chunk),'gain':gain})
    with wave.open(str(out/'aligned-narration.wav'),'wb') as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(sr);wav.writeframes((track*32767).astype('<i2').tobytes())
    run(['-safe','0','-f','concat','-i',listing,'-i',out/'aligned-narration.wav','-map','0:v:0','-map','1:a:0',
         '-c:v','copy','-c:a','aac','-b:a','128k','-movflags','+faststart',out/'rd-documentos.mp4'])
    run(['-i',out/'aligned-narration.wav','-c:a','libmp3lame','-b:a','128k',out/'narracion.mp3'])
    (out/'subtitulos.srt').write_text('\n'.join(subtitles))
    (out/'render.json').write_text(json.dumps({'edition':3 if a.calm else 2,'voice':narration['profile'],'duration':offset,'render_seconds':time.perf_counter()-started,
        'timeline':timeline,'cues':all_cues,'video_bytes':(out/'rd-documentos.mp4').stat().st_size,'width':720,'height':1280,'fps':30,
        'execution':'local timing and FFmpeg; no model APIs; audio speed unchanged','speech_lead':None if plan else lead,'editorial_plan':plan,'guide':a.guide,'pacing':'calm' if a.calm else 'v2','audio_sample_rate':sr,'audio_segments':audio_segments},ensure_ascii=False,indent=2)+'\n')
    sheet=Image.new('RGB',(1440,640))
    for i,scene in enumerate(timeline):
        target=parts/f'{scene["id"]}-preview.jpg'
        run(['-ss',str(scene['start']+scene['duration']*.55),'-i',out/'rd-documentos.mp4','-frames:v','1',target])
        sheet.paste(Image.open(target).resize((360,640)),(360*i,0))
    sheet.save(out/'vista-previa.jpg',quality=90)
if __name__=='__main__':main()
