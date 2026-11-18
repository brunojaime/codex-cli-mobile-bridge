"""Mix an authorized Eleven Music instrumental with the approved narration and effects."""
from pathlib import Path
import json,subprocess,hashlib,shutil
import numpy as np
import av,imageio_ffmpeg
root=Path(__file__).resolve().parents[3];out=root/'reports/videos/nienfos-presentacion-v10-groove';source=root/'reports/videos/nienfos-presentacion-v8-papel-clicks'
ffmpeg=imageio_ffmpeg.get_ffmpeg_exe();rate=44100
meta=json.loads((out/'music-generation.json').read_text());assert meta['status']=='generated','Music generation not yet authorized or complete'
def decode(path,channels=2,filters=None):
 args=[ffmpeg,'-v','error','-i',str(path),'-ar',str(rate),'-ac',str(channels)]
 if filters:args+=['-af',filters]
 raw=subprocess.check_output(args+['-f','f32le','pipe:1']);a=np.frombuffer(raw,dtype='<f4').copy()
 return a.reshape(-1,channels)
base=decode(out/'mezcla-sin-musica.wav');n=round(24.3*rate);assert abs(len(base)-n)<rate*.03;base=base[:n]
music=decode(out/'musica-original.mp3',filters='highpass=f=35,lowpass=f=12000,equalizer=f=105:t=o:w=1:g=2.5,equalizer=f=2300:t=o:w=1.3:g=-2.5')
assert len(music)/rate>=23.8,'Unexpected short music generation'
music=np.pad(music,((0,max(0,n-len(music))),(0,0)))[:n]
voice=decode(root/'reports/videos/nienfos-presentacion-v5-voces/mauricio/narracion.wav',channels=1)[:n,0]
active=np.abs(voice)>.015;voice_rms=float(np.sqrt(np.mean(voice[active]**2)))
music_rms=float(np.sqrt(np.mean(music**2)));assert music_rms>.001
# A steady bed under the narration; energy comes from arrangement and percussion.
target=voice_rms*10**(-12.0/20);gain=target/music_rms
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
subprocess.run([ffmpeg,'-v','error','-y','-i',str(out/'presentacion-sin-musica.mp4'),'-i',str(out/'mezcla.wav'),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k','-movflags','+faststart','-t','24.3',str(video)],check=True)
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
validation={'all_passed':True,'frames':count,'duration':duration,'size':[720,1280],'audio_streams':1,'subtitle_streams':0,'full_video_decode':True,'full_audio_decode':True,'video_packets_identical':True,'voice_gain_unchanged':True,'effects_revised':True,'bass_body_eq_db':2.5,'low_mid_eq_hz':105,'peak_after_aac':round(peak,5),'music_gain':gain,'music_headroom_factor':headroom,'music_rms_relative_to_active_voice_db':round(20*np.log10(np.sqrt(np.mean(music**2))/voice_rms),2),'music_provider':'ElevenLabs','music_model':meta['request']['model_id'],'reported_character_cost':meta.get('reported_character_cost')}
(out/'validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n')
for name in ['portada.jpg','escenas.jpg']:shutil.copy2(source/name,out/name)
(out/'README.md').write_text('''# Nienfos · Más groove, efectos más limpios

[Ver presentación](presentacion.mp4)

24,3 segundos · voz de Mauricio · sin subtítulos.

La música es una nueva variación de Eleven Music condicionada por la instrumental anterior. El encargo mantiene el carácter jazzero del piano y pide contrabajo más protagonista, batería más intensa con notas fantasma y redobles breves, e intercambio rítmico más juguetón. No se aislaron stems: la nueva interpretación puede cambiar también las frases del piano.

La mezcla da 1,5 dB más de presencia objetivo a la música respecto de la revisión anterior y realza suavemente el cuerpo a 105 Hz. La voz conserva su ganancia. El bajo y la batería se pidieron más presentes en la generación; no se afirma que un ecualizador modifique instrumentos por separado.

Los efectos se redujeron a apoyos de tarjeta, una hoja fina para la devolución de diseño y el clic aprobado en las confirmaciones. Se eliminaron los barridos sonoros, la textura de conector tipo cremallera y los roces del cierre. El logo termina con un clic breve.

[Escuchar la instrumental](musica-original.mp3) · [Ver sin música](presentacion-sin-musica.mp4) · [Escuchar solo efectos](solo-efectos.wav) · [Versión anterior](../nienfos-presentacion-v9-musica/presentacion.mp4)

![Escenas](escenas.jpg)

Verificación: decodificación completa de imagen y audio, duración, niveles sin saturación digital, cero pistas de subtítulos y H264 idéntico a la versión aprobada. Se verificaron mediciones y sincronización; no se declara escucha humana.

[Validación](validation.json) · [Validación de efectos](effects-validation.json) · [Efectos por fotograma](sound-plan.json) · [Generación musical](music-generation.json)

La referencia fue almacenada con el endpoint de carga y usada para una generación condicionada según la [guía oficial](https://elevenlabs.io/docs/eleven-api/guides/how-to/music/inpainting). Aplican las [condiciones de Eleven Music](https://elevenlabs.io/music-terms). La entrega conserva los archivos anteriores y no publica en plataformas externas.
''')
print(json.dumps(validation,ensure_ascii=False))
