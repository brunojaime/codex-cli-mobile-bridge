"""Extract the settled public-site recordings for deterministic Remotion playback."""
from pathlib import Path
import subprocess
import imageio_ffmpeg

assets=Path(__file__).resolve().parent/'public/campaign'
for name in ['hero','ocean']:
    target=assets/(name+'-frames')
    target.mkdir(exist_ok=True)
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-y','-sseof','-8',
      '-i',str(assets/(name+'-recording.webm')),'-an','-vf','fps=15,scale=1440:900',
      '-q:v','3','-start_number','0',str(target/'%03d.jpg')],check=True)
    assert len(list(target.glob('*.jpg')))==120
    print(name+': 120 frames, no initial loading screen')
