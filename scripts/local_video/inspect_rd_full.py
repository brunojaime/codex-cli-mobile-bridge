"""Decode the actual MP4, collect representative frames, and measure media. No visual verdict."""
from pathlib import Path
import argparse,json
import av,numpy as np
from PIL import Image,ImageDraw,ImageFont
from bookends import read_pcm,sha,SR
from guide_qc import captions,caption_checks,audio_checks,first_frame_ok
from rd_full_render import DEFAULT_SOURCE

def inspect(report):
    final=report/'final';movie=final/'rd-documentos-completo.mp4';meta=json.loads((final/'render.json').read_text())
    selected=['signature-fields','signature-preview-a','signature-change','signature-persist','templates-open','template-edit','template-new','template-subject','template-preview','template-created','template-switch','template-use','template-result']
    points=[('portada',0.)]+[(e['id'],e['end']-.65) for e in meta['timeline'] if e['id'] in selected]
    points.extend([('novedad-documento',meta['old_body_start']+12),('novedad-correo',meta['old_body_start']+22),('cierre',meta['duration']-1.5)])
    frames=report/'frames';frames.mkdir(exist_ok=True);targets={round(t*30):(name,t) for name,t in points};saved=[];count=0;first=None
    with av.open(str(movie)) as c:
        v=c.streams.video[0];duration=float(v.duration*v.time_base)
        for i,frame in enumerate(c.decode(video=0)):
            if i==0:first=frame.to_image()
            if i in targets:
                name,t=targets[i];frame.to_image().save(frames/f'{name}.jpg',quality=94);saved.append({'id':name,'time':i/30,'path':f'frames/{name}.jpg'})
            count+=1
    assert count==meta['frames'] and len(saved)==len(points)
    cols=4;tw=300;th=558;sheet=Image.new('RGB',(cols*tw,((len(saved)+cols-1)//cols)*th),'#e5e9ec');draw=ImageDraw.Draw(sheet);font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',13)
    for i,item in enumerate(saved):
        im=Image.open(report/item['path']);im.thumbnail((300,533));x=i%cols*tw;y=i//cols*th;sheet.paste(im,(x,y+25));draw.text((x+5,y+5),f"{item['time']:.1f}s · {item['id']}",font=font,fill='#102b43')
    sheet.save(report/'fotogramas.jpg',quality=94)
    # Actual sampled decoded pixels confirm the old novelty walkthrough was retained.
    indices={round(meta['old_source_start']*30)+k for k in range(0,1094,90)};originals={}
    with av.open(str(DEFAULT_SOURCE/'rd-documentos-completo.mp4')) as c:
        for i,f in enumerate(c.decode(video=0)):
            if i in indices:originals[i]=np.asarray(f.to_image()).astype(float)
    delta=round((meta['old_body_start']-meta['old_source_start'])*30);errors=[]
    with av.open(str(movie)) as c:
        for i,f in enumerate(c.decode(video=0)):
            if i-delta in originals:errors.append(float(np.abs(np.asarray(f.to_image()).astype(float)-originals[i-delta]).mean()))
    dry=read_pcm(final/'narracion.wav');mixed=read_pcm(final/'mezcla.wav');bed=read_pcm(final/'musica.wav')
    cc=caption_checks(captions(final/'subtitulos.srt'),duration);qc=audio_checks(dry)
    with av.open(str(movie)) as c:
        audio_duration=float(c.streams.audio[0].duration*c.streams.audio[0].time_base);decoded=np.concatenate([f.to_ndarray().reshape(-1) for f in c.decode(audio=0)])
    result={'video_sha256':sha(movie),'duration':duration,'video_frames':count,'audio_duration':audio_duration,'decoded_audio_peak':float(np.max(np.abs(decoded))),'captions':cc,'narration':qc,'mixed_peak':float(np.max(np.abs(mixed.astype(float))))/32768,'music_to_voice_rms_db':float(20*np.log10(np.sqrt(np.mean(bed.astype(float)**2))/np.sqrt(np.mean(dry.astype(float)**2)))),'approved_video_max_mean_pixel_error':max(errors),'old_pcm_identical':bool(np.array_equal(dry[round(meta['old_body_start']*SR):],read_pcm(DEFAULT_SOURCE/'narracion.wav')[round(meta['old_source_start']*SR):])),'title_visible_numeric':first_frame_ok(first),'frames_for_visual_review':saved,'visual_observation':'not performed by this script'}
    (report/'media-qc.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    assert cc['ordered'] and cc['readable'] and qc['valid'] and result['decoded_audio_peak']<1 and result['mixed_peak']<.97 and max(errors)<3 and result['old_pcm_identical']
    print(json.dumps({k:v for k,v in result.items() if k!='frames_for_visual_review'}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('report',type=Path);a=p.parse_args();inspect(a.report)
