#!/usr/bin/env python3
"""Real FFmpeg normalization smoke; generated tone only, no voice/model calls."""
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import wave
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from services.relevamientos.speech import Speech

def main():
    executable=Path(os.environ.get('RELEVAMIENTOS_FFMPEG',str(ROOT/'.data/relevamientos-tools/ffmpeg')))
    os.environ['RELEVAMIENTOS_FFMPEG']=str(executable)
    results=[]
    with tempfile.TemporaryDirectory() as tmp:
        folder=Path(tmp);source=folder/'tone.wav'
        with wave.open(str(source),'wb') as f:
            f.setparams((2,2,22050,0,'NONE','not compressed'))
            f.writeframes(b''.join(struct.pack('<hh',int(1000*math.sin(2*math.pi*440*i/22050)),0) for i in range(22050)))
        for ext in ('wav','mp3','m4a','mp4','mkv'):
            target=folder/('input.'+ext)
            subprocess.run([str(executable),'-v','error','-y','-i',str(source),str(target)],capture_output=True,check=True,timeout=30)
            output=folder/(ext+'.wav');Speech().normalize(target,output)
            with wave.open(str(output)) as f:
                row={'source_format':ext,'channels':f.getnchannels(),'sample_rate':f.getframerate(),'duration':f.getnframes()/f.getframerate()}
                assert row['channels']==1 and row['sample_rate']==16000 and .9<row['duration']<1.2
                results.append(row)
    print(json.dumps({'input':'generated synthetic stereo tone, no speech','results':results},indent=2))
    print('NIENFOS_OBSERVATIONS_V1 '+json.dumps({'observations':{'ffmpeg-formats':len(results)==5}}))
if __name__=='__main__':main()
