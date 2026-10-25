"""Executed media and integration evidence for the compact portrait template."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile

import av
import numpy as np
from PIL import Image,ImageFont
from bookends import sha
from guide_qc import inspect
from project import prepare
from screen_template import render,validate,subtitles,caption_rows,compose,FONT

ROOT=Path(__file__).resolve().parents[2]
REPORT=ROOT/'reports/rd-video-pantalla-grande-20260929'
SOURCE=ROOT/'reports/rd-video-musica-ajuste-20260929/final'
FINAL=REPORT/'final'
SKILL=ROOT/'scripts/local_video/skill/local-feature-videos'
INSTALLED=Path.home()/'.codex/skills/local-feature-videos'
facts={}

def audio_packets(path):
    with av.open(str(path)) as c:
        return [(p.pts,p.dts,p.duration,bytes(p)) for p in c.demux(audio=0) if p.size]

try:
    p=json.loads((REPORT/'template.json').read_text());rect=[68,99,584,978];target=validate(p,rect)
    area=target[2]*target[3]/(720*1280)
    assert area>=.85 and target[2]/720>=.95
    assert abs(target[2]/target[3]-rect[2]/rect[3])<.001
    meta=json.loads((SOURCE/'render.json').read_text());caps=subtitles(SOURCE/'subtitulos.srt')
    for start,end,text in caps:
        rows=caption_rows(text,ImageFont.truetype(FONT,p['caption_font']),684)
        assert len(rows)<=2 and 7+len(rows)*32<=p['caption_height']
    review=json.loads((REPORT/'visual-review.json').read_text())
    assert review['comparison_sha256']==sha(REPORT/'comparacion.jpg') and review['result']=='pass'
    assert review['video_sha256']==sha(FINAL/'rd-documentos-completo.mp4')
    facts['larger-app-screen']=True
    a=audio_packets(SOURCE/'rd-documentos-completo.mp4');b=audio_packets(FINAL/'rd-documentos-completo.mp4')
    assert len(a)==len(b) and a[:-1]==b[:-1]
    # FFmpeg normalizes the last packet's padding duration when remuxing MP4.
    # Encoded payloads and all timestamps must match, as must decoded audio.
    assert a[-1][:2]==b[-1][:2] and a[-1][3]==b[-1][3]
    decoded=[];durations=[]
    for folder in [SOURCE,FINAL]:
        with av.open(str(folder/'rd-documentos-completo.mp4')) as container:
            stream=container.streams.audio[0];durations.append(stream.duration*stream.time_base)
            decoded.append(np.concatenate([frame.to_ndarray() for frame in container.decode(audio=0)],axis=1))
    assert durations[0]==durations[1] and np.array_equal(*decoded)
    for name in ['narracion.wav','mezcla.wav','subtitulos.srt','intro.png','outro.png']:
        assert sha(SOURCE/name)==sha(FINAL/name)
    final_meta=json.loads((FINAL/'render.json').read_text())
    assert final_meta['cues']==meta['cues'] and final_meta['actions_plan']==meta['actions_plan']
    largest_error=0;count=0
    with av.open(str(SOURCE/'rd-documentos-completo.mp4')) as c,av.open(str(FINAL/'rd-documentos-completo.mp4')) as d:
        for old,new in zip(c.decode(video=0),d.decode(video=0),strict=True):
            assert old.time==new.time
            # Sample cards, every guide second and each pulse with a decoded-frame comparison.
            pulse=any(abs(float(old.time)-e['pulse_at'])<1/30 for e in meta['actions_plan']['actions'])
            if count%30==0 or pulse:
                expected=compose(old.to_image(),float(old.time),meta,p,rect,target,caps)
                error=float(np.abs(np.asarray(expected).astype(float)-np.asarray(new.to_image()).astype(float)).mean())
                largest_error=max(largest_error,error);assert error<3
            count+=1
    assert count==1199
    qc=inspect(FINAL,write=False);assert qc['duration']==meta['duration']
    facts['preserve-approved-content']=True
    default=json.loads((SKILL/'default-screen-template.json').read_text())
    for name in ['SKILL.md','screen-template.md','default-screen-template.json','pipeline.md','actions.md']:
        assert (SKILL/name).read_bytes()==(INSTALLED/name).read_bytes()
    subprocess.run([str(ROOT/'.venv/bin/python'),str(Path.home()/'.codex/skills/.system/skill-creator/scripts/quick_validate.py'),str(INSTALLED)],check=True)
    with tempfile.TemporaryDirectory(prefix='large-screen-check-') as temp:
        temp=Path(temp)
        for name in ['one','two']:
            w=temp/name;w.mkdir();r=prepare(w,'feature','DEMO','test:explicit')['request']
            assert r['screen_template']==default and r['source_ui_rect'] is None
            assert r['voice']=='voz-1' and r['music']['duck_db']==4 and not r['render_started']
        variant=copy.deepcopy(default);variant.update(client='Cliente DEMO',background='#142536',accent='#ffa84c')
        validate(variant,rect)
        compose(Image.new('RGB',(720,1280),'white'),5,meta,variant,rect,validate(variant,rect),caps)
        facts['reusable-screen-template']=True
        invalid=[]
        for key,value in [('margin',-1),('caption_font',12),('accent','oops'),('header_height',float('nan'))]:
            bad=copy.deepcopy(p);bad[key]=value;invalid.append((bad,rect))
        invalid.append((p,[700,100,300,700]))
        rejected=0
        for bad,r in invalid:
            try:validate(bad,r)
            except ValueError:rejected+=1
        assert rejected==5
        try:caption_rows('palabra '*100,ImageFont.truetype(FONT,27),684)
        except ValueError:rejected+=1
        assert rejected==6
        render(SOURCE,temp/'repeat',REPORT/'template.json',rect)
        assert sha(temp/'repeat/rd-documentos-completo.mp4')==sha(FINAL/'rd-documentos-completo.mp4')
    facts['screen-template-checks']=True
    print(json.dumps({'frames':count,'area_percent':area*100,'width_percent':target[2]/720*100,'maximum_mean_pixel_error':largest_error,'audio_packets_identical':True,'invalid_inputs_rejected':rejected,'scope':'local media and shared template'}))
finally:
    print('NIENFOS_OBSERVATIONS_V1 '+json.dumps({'observations':facts}))
