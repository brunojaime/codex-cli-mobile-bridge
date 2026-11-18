"""Isolated optional WhisperX worker; compatible model caches are reused."""
import json
import os
from pathlib import Path
import subprocess
from .core import atomic

class Speech:
    def normalize(self,source,target):
        subprocess.run([os.environ.get('RELEVAMIENTOS_FFMPEG','ffmpeg'),'-nostdin','-v','error','-protocol_whitelist','file,pipe','-i',str(source),'-vn','-ac','1','-ar','16000','-t',str(int(os.environ.get('RELEVAMIENTOS_MAX_SECONDS','14400'))+1),'-y',str(target)],check=True,timeout=1800,capture_output=True)
        import wave
        with wave.open(str(target)) as audio:
            if audio.getnframes()/audio.getframerate()>int(os.environ.get('RELEVAMIENTOS_MAX_SECONDS','14400')):
                raise ValueError('duration_limit')

    def invoke(self,stage,audio,aligned=None):
        request=audio.parent/(stage+'-request.json')
        response=audio.parent/(stage+'-response.json')
        atomic(request,{'stage':stage,'audio':str(audio.resolve()),'aligned':aligned,'output':str(response.resolve())})
        # Operator-controlled argv JSON, not a command derived from meeting content.
        command=json.loads(os.environ.get('RELEVAMIENTOS_SPEECH_ARGV','[".venv-relevamientos/bin/python", "-m", "services.relevamientos.speech"]'))
        subprocess.run([*command,str(request.resolve())],check=True,timeout=int(os.environ.get('RELEVAMIENTOS_SPEECH_TIMEOUT','14400')),capture_output=True)
        return json.loads(response.read_text())

    def transcribe(self,audio):return self.invoke('transcribe',audio)
    def diarize(self,audio,aligned):return self.invoke('diarize',audio,aligned)


def run(request):
    import whisperx
    import torch
    device='cuda' if torch.cuda.is_available() else 'cpu'
    audio=whisperx.load_audio(request['audio'])
    if request['stage']=='transcribe':
        model=whisperx.load_model(os.environ.get('RELEVAMIENTOS_ASR_MODEL','small'),device,compute_type='float16' if device=='cuda' else 'int8',language='es')
        result=model.transcribe(audio,batch_size=2,language='es')
        del model
        align,metadata=whisperx.load_align_model(language_code='es',device=device)
        result=whisperx.align(result['segments'],align,metadata,audio,device,return_char_alignments=False)
        atomic(request['output'],result)
    else:
        from whisperx.diarize import DiarizationPipeline
        diarizer=DiarizationPipeline(model_name='pyannote/speaker-diarization-community-1',token=os.environ['HF_TOKEN'],device=device)
        turns=diarizer(audio)
        result=whisperx.assign_word_speakers(turns,request['aligned'])
        rows=[]
        for i,s in enumerate(result['segments']):
            matching=turns[(turns.start<s['end']) & (turns.end>s['start'])]
            overlap=any(max(a.start,b.start)<min(a.end,b.end) for ai,a in matching.iterrows() for bi,b in matching.iterrows() if ai<bi and a.speaker!=b.speaker)
            rows.append({'id':f'S{i:06d}','start':s['start'],'end':s['end'],'text':s['text'],'speaker':s.get('speaker','SPEAKER_UNKNOWN'),'uncertain':'speaker' not in s or overlap,'overlap':overlap,'words':s.get('words',[])})
        atomic(request['output'],{'language':'es','segments':rows,'method':'WhisperX alignment + pyannote community-1; labels are not identities'})

if __name__=='__main__':
    import sys
    run(json.loads(Path(sys.argv[1]).read_text()))
