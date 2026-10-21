"""Local deterministic editorial checks. No model, network or transcription required."""
from pathlib import Path
import argparse,json,re
import av,numpy as np
from PIL import Image
from bookends import read_pcm,seconds,sha

def captions(path):
    result=[]
    for block in Path(path).read_text().strip().split('\n\n'):
        lines=block.splitlines();a,b=lines[1].split(' --> ')
        result.append({'start':seconds(a),'end':seconds(b),'text':' '.join(lines[2:])})
    return result

def first_frame_ok(im):
    # Title occupies this stable region of the minimal opening template.
    rgb=np.asarray(im.convert('RGB'))[390:580,60:660].astype(float)
    return float((rgb.mean(axis=2)<150).mean())>.035

def caption_checks(items,duration):
    spans=[c['end']-c['start'] for c in items]
    rates=[len(c['text'])/s if s>0 else float('inf') for c,s in zip(items,spans)]
    return {'ordered':all(0<=c['start']<c['end']<=duration+.002 for c in items) and all(a['end']<=b['start']+.001 for a,b in zip(items,items[1:])),
            'readable':bool(items) and min(spans)>=1.2 and max(rates)<=19.0,'maximum_characters_per_second':max(rates,default=0),'minimum_caption_seconds':min(spans,default=0)}

def audio_checks(pcm,sr=48000):
    x=pcm.astype(float)/32768
    n=len(x)//480;chunks=x[:n*480].reshape(n,480)
    quiet=np.sqrt(np.mean(chunks**2,axis=1))<10**(-45/20)
    longest=run=0
    for q in quiet:
        run=run+1 if q else 0;longest=max(longest,run)
    clipped=float((np.abs(x)>=.999).mean())
    return {'peak':float(np.abs(x).max()),'clipped_fraction':clipped,'longest_silence_seconds':longest*.01,'silence_limit_seconds':6.5,'valid':bool(clipped==0 and longest*.01<=6.5 and np.max(np.abs(x))>.05)}

def inspect(out,write=True):
    out=Path(out);movie=out/'rd-documentos-completo.mp4'
    with av.open(str(movie)) as c:
        v=c.streams.video[0];duration=float(v.duration*v.time_base);im=next(c.decode(video=0)).to_image()
    c=caption_checks(captions(out/'subtitulos.srt'),duration);a=audio_checks(read_pcm(out/'narracion.wav'))
    checks={'first_frame_has_title':first_frame_ok(im),'under_one_minute':duration<60,'captions_ordered':c['ordered'],'captions_readable':c['readable'],'audio_without_clipping_or_excessive_silence':a['valid']}
    result={'video_sha256':sha(movie),'duration':duration,'checks':checks,'captions':c,'audio':a,'method':'Local pixels, SRT and PCM; silence is RMS below -45 dBFS in 10 ms windows. Limit 6.5 s preserves approved reading pauses.'}
    if write:
        im.save(out/'portada.jpg',quality=95);(out/'guide-qc.json').write_text(json.dumps(result,indent=2)+'\n')
    assert all(checks.values()),result
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args();print(json.dumps(inspect(a.output)))
