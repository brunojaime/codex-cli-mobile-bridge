"""Replace only two narration phrases; stream-copy the approved visual edit."""
import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

import av
import numpy as np
from bookends import ROOT, SR, command, read_pcm, write_pcm, sha

SOURCE = ROOT / 'reports/rd-tutorial-completo-20260930/final'
REPORT = ROOT / 'reports/rd-pronunciacion-20260930'
IDS = ('intro', 'signature-preview-a')


def render(output):
    output = output.resolve()
    if output == SOURCE.resolve():
        raise ValueError('Preserve the approved source')
    recipe = json.loads((REPORT / 'voice-recipe.json').read_text())
    assert tuple(s['id'] for s in recipe['scenes']) == IDS
    meta = json.loads((SOURCE / 'render.json').read_text())
    dry = read_pcm(SOURCE / 'narracion.wav').copy()
    changes = []
    for scene in recipe['scenes']:
        e = next(e for e in meta['timeline'] if e['id'] == scene['id'])
        voice = read_pcm(REPORT / 'audio' / (scene['id'] + '.wav'))
        x = voice.astype(float) / 32768
        gain = min(.10 / max(np.sqrt(np.mean(x*x)), 1e-6), .85 / max(np.max(np.abs(x)), 1e-6))
        start = round(e['voice_start'] * SR)
        old_end = round(e['voice_end'] * SR)
        end = start + len(voice)
        if end / SR > e['end'] - .25:
            raise ValueError('Natural speech does not fit existing scene: ' + scene['id'])
        dry[start:max(end, old_end)] = 0
        dry[start:end] = np.round(voice * gain).astype('<i2')
        changes.append({'id':scene['id'], 'display_text':scene['display_text'], 'spoken_text':scene['text'],
                        'start_sample':start, 'end_sample':max(end,old_end), 'voice_end':end/SR,
                        'scene_end':e['end'], 'gain':float(gain), 'audio_sha256':sha(REPORT/'audio'/(scene['id']+'.wav'))})
    # Reuse the exact approved music samples, without loudness recalibration.
    music = read_pcm(SOURCE / 'musica.wav')
    mixed = dry.astype(np.int32) + music.astype(np.int32)
    assert np.max(np.abs(mixed)) < .97 * 32768
    output.mkdir(parents=True, exist_ok=True)
    for name in ('subtitulos.srt', 'portada.jpg', 'intro.png', 'outro.png', 'musica.wav'):
        shutil.copyfile(SOURCE/name, output/name)
    write_pcm(output/'narracion.wav', dry)
    write_pcm(output/'mezcla.wav', mixed)
    command(['-i',SOURCE/'rd-documentos-completo.mp4','-i',output/'mezcla.wav',
             '-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','128k',
             '-movflags','+faststart',output/'rd-documentos-completo.mp4'])
    for change in changes:
        start,end=change['start_sample'],change['end_sample']
        write_pcm(output/(change['id']+'-antes.wav'),read_pcm(SOURCE/'narracion.wav')[start:end])
        write_pcm(output/(change['id']+'-despues.wav'),dry[start:end])
    result={'source_video_sha256':sha(SOURCE/'rd-documentos-completo.mp4'),
            'video_sha256':sha(output/'rd-documentos-completo.mp4'),'changes':changes,
            'voice':'voz-1','speed':1,'pitch_shift':0,'duration':meta['duration'],
            'model_api_calls':0,'music_samples_preserved':True}
    (output/'patch.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result


def align():
    os.environ.update(HF_HUB_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1')
    def offline(event, values):
        if event in ('socket.connect','socket.getaddrinfo'):
            raise RuntimeError('Offline transcription blocks network')
    sys.addaudithook(offline)
    from faster_whisper import WhisperModel
    model=WhisperModel('small',device='cpu',compute_type='int8',cpu_threads=1,num_workers=1,local_files_only=True)
    results=[]
    # Transcribe the patched dry samples, with no text prompt suggesting the answer.
    for id in IDS:
        wav=REPORT/'final'/(id+'-despues.wav')
        segments,_=model.transcribe(str(wav),language='es',beam_size=5,word_timestamps=True)
        words=[{'word':w.word.strip(),'start':w.start,'end':w.end} for s in segments for w in s.words]
        results.append({'id':id,'audio_sha256':sha(wav),'transcript':' '.join(w['word'] for w in words),'words':words})
    (REPORT/'pronunciation-transcript.json').write_text(json.dumps({'method':'Whisper small local offline, no initial prompt; instrumental evidence, not human listening','scenes':results},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(results,ensure_ascii=False))


def video_digest(path):
    h=hashlib.sha256();sizes=[]
    with av.open(str(path)) as c:
        stream=c.streams.video[0]
        info=(stream.width,stream.height,stream.frames,float(stream.duration*stream.time_base))
        for p in c.demux(stream):
            h.update(bytes(p));sizes.append(p.size)
    return h.hexdigest(),info,sizes


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=REPORT/'final');p.add_argument('--align',action='store_true')
    a=p.parse_args()
    if a.align:align()
    else:print(json.dumps(render(a.output),ensure_ascii=False))
