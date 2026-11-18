"""Decode the silent institutional export and extract actual review frames."""
from pathlib import Path
import hashlib
import json
import sys

import av
import numpy as np
from PIL import Image, ImageDraw

out = Path(sys.argv[1]).resolve()
movie = out/'institucional.mp4'
selected = {0:'portada.png',45:'escena-1.jpg',125:'escena-2.jpg',210:'escena-3.jpg',280:'escena-4.jpg',370:'escena-5.jpg'}
images = {}
with av.open(str(movie)) as c:
    assert len(c.streams.audio) == 0, 'The delivered file must have no audio track'
    video = c.streams.video[0]
    assert (video.width, video.height) == (720,1280)
    assert abs(float(video.duration*video.time_base)-14)<.05
    frames=0
    for i,frame in enumerate(c.decode(video=0)):
        frames += 1
        if i in selected:
            images[i]=frame.to_image()
            images[i].save(out/selected[i])
    assert frames==420
opening=np.array(images[0])[280:550,54:666].astype(float)
visible=float(np.mean(np.max(np.abs(opening-np.array([20,43,52])),axis=2)>40))
assert visible>.01, 'Opening title must already be visible at frame zero'
board=Image.new('RGB',(720,930),'#e7e9e6')
draw=ImageDraw.Draw(board)
for n,(frame,im) in enumerate(images.items()):
    thumbnail=im.copy();thumbnail.thumbnail((240,427))
    x=(n%3)*240;y=(n//3)*465
    draw.text((x+12,y+10),f'{frame/30:.1f}s',fill='#142b34')
    board.paste(thumbnail,(x,y+30))
board.save(out/'revision-escenas.jpg')
result={'duration_seconds':14,'fps':30,'decoded_frames':frames,'resolution':[720,1280],
    'audio_streams':0,'opening_title_visible_fraction':visible,'review_frames':list(selected),
    'sha256':hashlib.sha256(movie.read_bytes()).hexdigest(),
    'checks':{'full_decode':True,'no_audio_track':True,'title_visible_at_start':True}}
(out/'validation.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
