"""Mix and verify the actual V20 deliverable, independently of the renderer."""
from pathlib import Path
import hashlib,json,subprocess
import av,imageio_ffmpeg,numpy as np
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'reports/videos/nienfos-v20-crecer'
FF=imageio_ffmpeg.get_ffmpeg_exe()
T=json.loads((OUT/'timing.json').read_text())
RATE=48000
N=T['frames']*1600
def run(args):
    return subprocess.run([FF,'-v','error','-y']+args,check=True,capture_output=True)
def decode(path,filters=None):
    args=['-i',str(path),'-ar',str(RATE),'-ac','2']
    if filters: args+=['-af',filters]
    return np.frombuffer(run(args+['-f','f32le','pipe:1']).stdout,dtype='<f4').reshape(-1,2).copy()
def save(name,samples):
    raw=OUT/(name+'.f32');raw.write_bytes(samples.astype('<f4').tobytes())
    run(['-f','f32le','-ar',str(RATE),'-ac','2','-i',str(raw),'-c:a','pcm_s24le',str(OUT/(name+'.wav'))]);raw.unlink()

voice=decode(OUT/'locucion.mp3','loudnorm=I=-17:TP=-3:LRA=9')
lead=round(T['lead']*RATE)
assert len(voice)+lead<N,'Voice must finish before final hold'
v=np.zeros((N,2),dtype=np.float32);v[lead:lead+len(voice)]=voice
music=decode(OUT/'musica.mp3','loudnorm=I=-27:TP=-6:LRA=8')
music=np.pad(music,((0,max(0,N-len(music))),(0,0)))[:N]
# Smooth envelope from isolated narration; music breathes around the whole take.
hop=480;blocks=int(np.ceil(N/hop))
rms=np.array([np.sqrt(np.mean(v[i*hop:min(N,(i+1)*hop)]**2)) for i in range(blocks)])
activity=np.minimum(1,rms/.025)
kernel=np.ones(41)/41
activity=np.convolve(activity,kernel,mode='same')
duck=np.interp(np.arange(N),np.arange(blocks)*hop,1-.52*activity)
fade=np.minimum(1,np.arange(N)/(RATE*.12))*np.minimum(1,(N-1-np.arange(N))/(RATE*.85))
m=music*duck[:,None]*fade[:,None]
mix=v+m
gain=min(1,.88/np.max(np.abs(mix)))
mix*=gain;v*=gain
save('narracion',v);save('mezcla',mix)
for filename,audio in [('propuesta.mp4','mezcla.wav'),('sin-musica.mp4','narracion.wav')]:
    run(['-i',str(OUT/'visual-sin-audio.mp4'),'-i',str(OUT/audio),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k','-t',str(T['duration']),'-movflags','+faststart',str(OUT/filename)])

movie=OUT/'propuesta.mp4'
targets={0:'portada',85:'gancho',135:'mensajes',188:'problema',235:'giro',320:'oficio',375:'escucha',406:'diseno',454:'integracion',518:'proyectos',612:'futuro',714:'cierre'}
samples={};black=[];count=0
with av.open(str(movie)) as c:
    stream=c.streams.video[0]
    assert (stream.width,stream.height)==(1080,1920)
    assert float(stream.average_rate)==30
    assert len(c.streams.audio)==1 and len(c.streams.subtitles)==0
    for frame in c.decode(video=0):
        if count in targets:
            im=frame.to_image();im.save(OUT/(targets[count]+'.jpg'),quality=93);samples[targets[count]]=im
        if count%15==0:
            small=np.array(frame.to_image().resize((54,96)))
            if small.mean()<3:black.append(count)
        count+=1
assert count==T['frames'] and not black
with av.open(str(movie)) as c:
    decoded_audio=sum(1 for _ in c.decode(audio=0))
assert decoded_audio>0
final=decode(movie)
peak=float(np.max(np.abs(final)))
assert peak<.99
assert abs(len(final)/RATE-T['duration'])<.06
names=['gancho','mensajes','problema','giro','oficio','escucha','diseno','integracion','proyectos','futuro','cierre']
board=Image.new('RGB',(220*len(names),420),paper:='#e4e9e6');draw=ImageDraw.Draw(board)
font=ImageFont.truetype('/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf',14)
for i,name in enumerate(names):
    im=samples[name].copy();im.thumbnail((220,391));board.paste(im,(220*i,26));draw.text((220*i+9,5),name,font=font,fill='#132b34')
board.save(OUT/'escenas.jpg',quality=94)
mobile_names=['gancho','problema','giro','oficio','diseno','integracion','proyectos','futuro','cierre']
mobile=Image.new('RGB',(1080,2010),'#e4e9e6');md=ImageDraw.Draw(mobile)
for i,name in enumerate(mobile_names):
    x=(i%3)*360;y=(i//3)*670
    im=samples[name].resize((360,640));mobile.paste(im,(x,y+30));md.text((x+12,y+6),name,font=font,fill='#132b34')
mobile.save(OUT/'storyboard.jpg',quality=94)
asr=json.loads((OUT/'transcription-check.json').read_text()) if (OUT/'transcription-check.json').exists() else None
if asr:assert asr['similarity']>.9
meta=json.loads((OUT/'locucion-generation.json').read_text())
report={'all_passed':True,'duration_seconds':T['duration'],'resolution':[1080,1920],
        'frames':count,'fps':30,'full_video_decode':True,'full_audio_decode':True,
        'sampled_black_frames':black,'peak_after_aac':peak,'audio_duration_seconds':len(final)/RATE,
        'continuous_narration':True,'internal_voice_cuts':0,'voice_speed_in_post':1.0,
        'music_ducking':True,'final_logo_hold_seconds':round(T['duration']-T['beats']['Nienfos. Hablemos'],3),
        'new_tts_calls':1,'new_music_calls':1,'tts_reported_cost':meta['reported_character_cost'],
        'music_reported_cost':None,'transcription_similarity':asr['similarity'] if asr else None,
        'human_listening_performed':False,
        'render_pipeline':{'parallel_encoding':False,'shared_memory_capture':False,'concurrency':4,
                           'exact_frame_recovered_in_fresh_browser':611,
                           'static_closing_hold_frames':[714,765],'recovery_evidence':'render-recovery.json'},
        'sha256':hashlib.sha256(movie.read_bytes()).hexdigest()}
(OUT/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False))
