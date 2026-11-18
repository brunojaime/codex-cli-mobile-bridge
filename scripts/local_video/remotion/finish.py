"""Mix approved local narration/music into the Remotion visual draft."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

import av
import numpy as np

ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE))
from music import components, integrated_lufs
from bookends import FF, SR, write_pcm


def main():
    out = Path(sys.argv[1]).resolve()
    source = out / 'visual-sin-audio.mp4'
    meta = json.loads((out/'voice/narration.json').read_text())
    dry = np.zeros(24 * SR, dtype='<i2')
    timings = []
    subtitles = []
    for i, entry in enumerate(meta['entries']):
        pcm = subprocess.run([FF, '-v', 'error', '-i', str(out/'voice'/entry['deliverable']),
            '-f', 's16le', '-ar', str(SR), '-ac', '1', '-'], check=True, capture_output=True).stdout
        samples = np.frombuffer(pcm, dtype='<i2')
        start = i*6 + .6
        end = start + len(samples)/SR
        if end > (i+1)*6 - .15:
            raise ValueError(f'Scene {i+1} needs more reading time: {end-start:.2f}s')
        offset = round(start * SR)
        dry[offset:offset+len(samples)] = samples
        timings.append({'start':start, 'end':end, 'text':entry['text']})
        def stamp(seconds):
            ms = round(seconds*1000)
            return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
        subtitles.append(f"{i+1}\n{stamp(start)} --> {stamp(end)}\n{entry['text']}\n")
    write_pcm(out/'narracion.wav', dry)
    (out/'subtitulos.srt').write_text('\n'.join(subtitles))
    cfg = json.loads((ENGINE/'skill/local-feature-videos/default-music-plan.json').read_text())
    music, info = components(dry, cfg)
    reference, _ = components(dry, {**cfg, 'mode':'soft-ambient'})
    gain = integrated_lufs(reference) - integrated_lufs(music)
    music = np.round(music.astype(float)*10**(gain/20)).astype('<i2')
    mixed = dry.astype(np.int32)+music.astype(np.int32)
    if np.max(np.abs(mixed)) >= .97*32768:
        raise ValueError('Insufficient audio headroom')
    write_pcm(out/'musica.wav', music)
    write_pcm(out/'mezcla.wav', mixed)
    for wav, name in [('narracion.wav','institucional-sin-musica.mp4'),('mezcla.wav','institucional.mp4')]:
        subprocess.run([FF,'-v','error','-y','-i',str(source),'-i',str(out/wav),'-map','0:v:0','-map','1:a:0',
            '-c:v','copy','-c:a','aac','-b:a','160k','-movflags','+faststart',str(out/name)],check=True)
    movie = out/'institucional.mp4'
    # Decode every video/audio frame to verify the actual deliverable.
    subprocess.run([FF,'-v','error','-i',str(movie),'-f','null','-'],check=True,capture_output=True)
    with av.open(str(movie)) as container:
        video = container.streams.video[0]
        duration = float(video.duration*video.time_base)
        assert (video.width, video.height) == (720,1280)
        assert abs(duration-24)<.05
        assert len(container.streams.audio)==1
    result = {'engine':'Remotion 4.0.540 + local FFmpeg audio mux', 'draft':True,
        'brand_assumption':'Nienfos; awaiting user brief', 'duration_seconds':duration,
        'size':[720,1280], 'fps':30, 'narration_profile':meta['profile'], 'timings':timings,
        'music_plan':cfg, 'music_calibration_db':gain,
        'mixed_peak':float(np.max(np.abs(mixed)))/32768,
        'sha256':hashlib.sha256(movie.read_bytes()).hexdigest(),
        'checks':{'full_decode':True,'audio_headroom':True,'speech_fits_scenes':True},
        'review_limits':'Frames inspected; no claim of listening evaluation.',
        'external_model_api_calls':0}
    (out/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))


if __name__ == '__main__':
    main()
