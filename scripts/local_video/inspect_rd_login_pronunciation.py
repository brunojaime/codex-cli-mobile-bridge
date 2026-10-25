"""Measure the correction and extract frames from the delivered MP4."""
import json
import av
import numpy as np
from PIL import Image, ImageDraw
from rd_login_pronunciation import REPORT, SOURCE, video_digest
from bookends import read_pcm, sha
from guide_qc import inspect, audio_checks

final = REPORT/'final'
movie = final/'rd-documentos-completo.mp4'
qc = inspect(final)
patch = json.loads((final/'patch.json').read_text())
dry = read_pcm(final/'narracion.wav')
old = read_pcm(SOURCE/'narracion.wav')
keep = np.ones(len(dry), dtype=bool)
for change in patch['changes']:
    keep[change['start_sample']:change['end_sample']] = False
qc.update(video_stream_identical=video_digest(movie)==video_digest(SOURCE/'rd-documentos-completo.mp4'),
          music_identical=sha(final/'musica.wav')==sha(SOURCE/'musica.wav'),
          captions_identical=sha(final/'subtitulos.srt')==sha(SOURCE/'subtitulos.srt'),
          other_narration_identical=bool(np.array_equal(dry[keep],old[keep])),
          mix=audio_checks(read_pcm(final/'mezcla.wav')),
          changes=patch['changes'])
with av.open(str(movie)) as container:
    stream=container.streams.audio[0]
    qc['audio_duration']=float(stream.duration*stream.time_base)
    samples=np.concatenate([frame.to_ndarray().reshape(-1) for frame in container.decode(audio=0)])
    qc['decoded_audio_peak']=float(np.max(np.abs(samples)))
(REPORT/'media-qc.json').write_text(json.dumps(qc,ensure_ascii=False,indent=2)+'\n')
frames=REPORT/'frames';frames.mkdir(exist_ok=True)
times=[0,5,10,15,29,50]
sheet=Image.new('RGB',(1080,355),'#eeeeee');draw=ImageDraw.Draw(sheet)
hashes={}
with av.open(str(movie)) as container:
    pending=iter(enumerate(times));index,target=next(pending)
    for frame in container.decode(video=0):
        if float(frame.time)+.001<target:continue
        image=frame.to_image();path=frames/f'{index:02d}-{target}s.jpg';image.save(path,quality=93)
        hashes[str(path.relative_to(REPORT))]=sha(path)
        image.thumbnail((180,620));sheet.paste(image,(index*180,25));draw.text((index*180+5,5),f'{target}s',fill='black')
        try:index,target=next(pending)
        except StopIteration:break
sheet.save(REPORT/'fotogramas.jpg',quality=93)
(REPORT/'frame-hashes.json').write_text(json.dumps(hashes,indent=2)+'\n')
print(json.dumps({k:v for k,v in qc.items() if k!='changes'},ensure_ascii=False))
