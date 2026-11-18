"""Compose recorded RD UI, local narration and readable captions with FFmpeg."""
from pathlib import Path
import argparse, json, subprocess, time, wave
from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg

ROOT = Path(__file__).resolve().parent
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
def run(args):
    subprocess.run([FFMPEG, '-hide_banner', '-loglevel', 'error', '-y', *map(str,args)], check=True)
def quoted(path):
    return "'"+str(path.resolve()).replace("'", "'\\''")+"'"
def stamp(seconds):
    ms=round(seconds*1000); return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--output',type=Path,required=True)
    p.add_argument('--recipe',type=Path,default=ROOT/'rd-documents.json'); a=p.parse_args()
    out=a.output.resolve(); recipe=json.loads(a.recipe.read_text()); parts=out/'edit'; parts.mkdir(exist_ok=True)
    started=time.perf_counter(); timeline=[]; subtitles=[]; offset=0
    for scene in recipe['scenes']:
        sid=scene['id']; capture=out/'capture'/sid
        frames=json.loads((capture/'frames.json').read_text()); lines=['ffconcat version 1.0']
        normalized=parts/f'{sid}-frames'; normalized.mkdir(exist_ok=True)
        # CDP can switch DPR during page.screenshot; constant dimensions avoid filter resets.
        for frame in frames['frames']:
            Image.open(capture/frame['file']).resize((584,978),Image.Resampling.LANCZOS).save(normalized/frame['file'],quality=95)
        for i,frame in enumerate(frames['frames']):
            duration=frames['frames'][i+1]['timestamp']-frame['timestamp'] if i+1<len(frames['frames']) else 1
            lines += ['file '+quoted(normalized/frame['file']), f'duration {max(.02,duration):.6f}']
        lines+=['file '+quoted(normalized/frames['frames'][-1]['file'])]
        listing=parts/f'{sid}.ffconcat'; listing.write_text('\n'.join(lines)+'\n')
        with wave.open(str(out/'audio'/f'{sid}.wav')) as wav: spoken=wav.getnframes()/wav.getframerate()
        duration=max(frames['duration'],spoken+1.3)
        # Portrait composition: actual mobile viewport occupies 584 x 978 pixels.
        card=Image.new('RGB',(720,1280),'#102b43'); d=ImageDraw.Draw(card)
        d.text((34,16),'RD  /  GESTIÓN DOCUMENTAL',font=ImageFont.truetype(BOLD,18),fill='#69d4e6')
        d.text((34,46),scene['title'],font=ImageFont.truetype(BOLD,27),fill='white')
        d.rounded_rectangle((63,94,657,1083),radius=20,fill='#47708b')
        d.text((34,1246),'DEMO · datos de ejemplo · sin envío real',font=ImageFont.truetype(FONT,19),fill='#a7c5d8')
        font=ImageFont.truetype(FONT,27); rows=[]; row=''
        for word in scene['text'].split():
            candidate=(row+' '+word).strip()
            if d.textlength(candidate,font=font)>650: rows.append(row); row=word
            else: row=candidate
        rows.append(row)
        for i,row in enumerate(rows): d.text((34,1104+i*37),row,font=font,fill='white')
        card.save(parts/f'{sid}.png')
        target=parts/f'{sid}.mp4'
        graph=(f'[1:v]scale=584:978,setsar=1,fps=25,tpad=stop_mode=clone:stop_duration={duration}[ui];'
               f'[0:v][ui]overlay=68:99,trim=duration={duration},format=yuv420p[v];'
               f'[2:a]loudnorm=I=-18:TP=-2:LRA=7,aresample=48000,adelay=600:all=1,apad=whole_dur={duration},atrim=duration={duration}[a]')
        run(['-threads','1','-loop','1','-framerate','25','-t',f'{duration:.3f}','-i',parts/f'{sid}.png','-threads','1','-safe','0','-f','concat','-i',listing,
             '-i',out/'audio'/f'{sid}.wav','-filter_complex_threads','1','-filter_complex',graph,
             '-progress',parts/f'{sid}-progress.txt','-map','[v]','-map','[a]','-t',f'{duration:.3f}','-c:v','libx264','-preset','veryfast','-crf','21',
             '-threads','2','-c:a','aac','-b:a','128k','-movflags','+faststart',target])
        timeline.append({'id':sid,'start':offset,'duration':duration,'speech_seconds':spoken})
        subtitles.append(f'{len(timeline)}\n{stamp(offset+.6)} --> {stamp(offset+.6+spoken)}\n{scene["text"]}\n')
        offset+=duration
        print(f'{sid}: {duration:.2f}s',flush=True)
    concat=parts/'final.ffconcat'; concat.write_text('ffconcat version 1.0\n'+'\n'.join('file '+quoted(parts/f'{s["id"]}.mp4') for s in recipe['scenes'])+'\n')
    run(['-safe','0','-f','concat','-i',concat,'-c','copy','-movflags','+faststart',out/'rd-documentos.mp4'])
    run(['-i',out/'rd-documentos.mp4','-vn','-c:a','libmp3lame','-b:a','128k',out/'narracion.mp3'])
    (out/'subtitulos.srt').write_text('\n'.join(subtitles))
    thumbs=[]
    for scene in timeline:
        target=parts/f'{scene["id"]}-preview.jpg'
        run(['-ss',f'{scene["start"]+scene["duration"]*.65:.3f}','-i',out/'rd-documentos.mp4','-frames:v','1',target])
        thumbs.append(Image.open(target).resize((360,640)))
    sheet=Image.new('RGB',(1440,640));
    for i,im in enumerate(thumbs): sheet.paste(im,(360*i,0))
    sheet.save(out/'vista-previa.jpg',quality=90)
    (out/'render.json').write_text(json.dumps({'voice':json.loads((out/'audio/narration.json').read_text())['profile'],
        'duration':offset,'render_seconds':time.perf_counter()-started,'timeline':timeline,
        'video_bytes':(out/'rd-documentos.mp4').stat().st_size,'width':720,'height':1280,
        'execution':'local FFmpeg; no model APIs'},indent=2)+'\n')
if __name__=='__main__': main()
