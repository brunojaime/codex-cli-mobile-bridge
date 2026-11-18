"""Mix an authorized Eleven Music instrumental with the approved narration and effects."""
from pathlib import Path
import json,subprocess,hashlib,shutil
import numpy as np
import av,imageio_ffmpeg
root=Path(__file__).resolve().parents[3];out=root/'reports/videos/nienfos-presentacion-v9-musica';source=root/'reports/videos/nienfos-presentacion-v8-papel-clicks'
ffmpeg=imageio_ffmpeg.get_ffmpeg_exe();rate=44100
meta=json.loads((out/'music-generation.json').read_text());assert meta['status']=='generated','Music generation not yet authorized or complete'
def decode(path,channels=2,filters=None):
 args=[ffmpeg,'-v','error','-i',str(path),'-ar',str(rate),'-ac',str(channels)]
 if filters:args+=['-af',filters]
 raw=subprocess.check_output(args+['-f','f32le','pipe:1']);a=np.frombuffer(raw,dtype='<f4').copy()
 return a.reshape(-1,channels)
base=decode(source/'mezcla.wav');n=round(24.3*rate);assert abs(len(base)-n)<rate*.03;base=base[:n]
music=decode(out/'musica-original.mp3',filters='highpass=f=55,lowpass=f=11000,equalizer=f=2500:t=o:w=1.5:g=-3')
assert len(music)/rate>=23.8,'Unexpected short music generation'
music=np.pad(music,((0,max(0,n-len(music))),(0,0)))[:n]
voice=decode(root/'reports/videos/nienfos-presentacion-v5-voces/mauricio/narracion.wav',channels=1)[:n,0]
active=np.abs(voice)>.015;voice_rms=float(np.sqrt(np.mean(voice[active]**2)))
music_rms=float(np.sqrt(np.mean(music**2)));assert music_rms>.001
# A steady bed under the narration; energy comes from arrangement and percussion.
target=voice_rms*10**(-13.5/20);gain=target/music_rms
music*=gain
fade_in=int(.12*rate);fade_out=int(.65*rate)
music[:fade_in]*=np.linspace(0,1,fade_in)[:,None];music[-fade_out:]*=np.linspace(1,0,fade_out)[:,None]
# Small intentional lift after the final sentence, not repeated pumping between phrases.
last_voice_end=23.30
lift=1+.20*np.clip((np.arange(n)/rate-last_voice_end)/.25,0,1);music*=lift[:,None]
headroom=1.
while np.max(np.abs(base+music*headroom))>.94:
 headroom*=.92;assert headroom>.1,'Music exceeds available headroom'
music*=headroom;mixed=base+music
assert np.isfinite(mixed).all() and np.max(np.abs(mixed))<=.941
raw=out/'mezcla.f32';raw.write_bytes(mixed.astype('<f4').tobytes())
subprocess.run([ffmpeg,'-v','error','-y','-f','f32le','-ar',str(rate),'-ac','2','-i',str(raw),'-c:a','pcm_s24le',str(out/'mezcla.wav')],check=True);raw.unlink()
video=out/'presentacion.mp4'
subprocess.run([ffmpeg,'-v','error','-y','-i',str(source/'presentacion.mp4'),'-i',str(out/'mezcla.wav'),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k','-movflags','+faststart','-t','24.3',str(video)],check=True)
def packet_hash(path):
 h=hashlib.sha256()
 with av.open(str(path)) as c:
  for packet in c.demux(video=0):h.update(bytes(packet))
 return h.hexdigest()
assert packet_hash(video)==packet_hash(source/'presentacion.mp4')
with av.open(str(video)) as c:
 assert len(c.streams.video)==1 and len(c.streams.audio)==1 and len(c.streams.subtitles)==0
 stream=c.streams.video[0];assert (stream.width,stream.height)==(720,1280)
 duration=float(stream.duration*stream.time_base);assert abs(duration-24.3)<.03
 count=sum(1 for _ in c.decode(video=0));assert count==729
with av.open(str(video)) as c:assert sum(1 for _ in c.decode(audio=0))>0
final=decode(video);peak=float(np.max(np.abs(final)));assert peak<.99
validation={'all_passed':True,'frames':count,'duration':duration,'size':[720,1280],'audio_streams':1,'subtitle_streams':0,'full_video_decode':True,'full_audio_decode':True,'video_packets_identical':True,'approved_voice_and_effects_gain_unchanged':True,'peak_after_aac':round(peak,5),'music_gain':gain,'music_headroom_factor':headroom,'music_rms_relative_to_active_voice_db':round(20*np.log10(np.sqrt(np.mean(music**2))/voice_rms),2),'music_provider':'ElevenLabs','music_model':meta['request']['model_id'],'reported_character_cost':meta.get('reported_character_cost')}
(out/'validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n')
for name in ['portada.jpg','escenas.jpg']:shutil.copy2(source/name,out/name)
(out/'README.md').write_text('''# Nienfos · Jazz con groove y energía

[Ver presentación con música](presentacion.mp4)

24,3 segundos · voz de Mauricio · hojas y clics aprobados · sin subtítulos.

Base instrumental original generada con Eleven Music. El encargo pide nu-jazz / jazz-funk a unos 118–120 BPM: piano acústico con acordes extendidos y frases rítmicas, contrabajo de madera con groove, batería con notas fantasma y redobles juguetones, y un toque electrónico discreto. La intención es transmitir iniciativa y musicalidad desde el comienzo. Los instrumentos y el BPM describen el encargo; no constituyen una evaluación auditiva humana ni una medición garantizada.

La mezcla se hizo con FFmpeg y procesamiento local. La voz y los efectos mantienen su ganancia; la música tiene espacio en frecuencias medias para la narración y un cierre con salida gradual. Se verificaron niveles, duración y decodificación; esto no equivale a una evaluación auditiva humana.

[Escuchar la música instrumental](musica-original.mp3) · [Comparar sin música](../nienfos-presentacion-v8-papel-clicks/presentacion.mp4)

![Escenas](escenas.jpg)

[Validación](validation.json) · [Encargo y procedencia](music-generation.json)

Herramienta elegida: [Eleven Music API](https://elevenlabs.io/docs/api-reference/music/compose). También se revisaron [Suno](https://help.suno.com/en/articles/9601665) y [SOUNDRAW](https://soundraw.io/license). Para este flujo se eligió Eleven Music por la integración existente, salida instrumental y duración configurable; no se afirma que sea superior en una prueba auditiva comparativa.

[Condiciones de Eleven Music](https://elevenlabs.io/music-terms): los derechos dependen del plan, la elegibilidad del titular y el medio de publicación. Starter contempla uso individual y tiene limitaciones para cine, TV, radio y distribución musical. Esta entrega no publica ni distribuye el video fuera del workspace.
''')
print(json.dumps(validation,ensure_ascii=False))
