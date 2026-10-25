"""Replay and verify the surgical pronunciation edit without new synthesis."""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
import av
import numpy as np
from bookends import SR, sha, read_pcm
from rd_pronunciation import REPORT, SOURCE, IDS, render, video_digest
from guide_qc import captions, caption_checks

facts={}
try:
    final=REPORT/'final';movie=final/'rd-documentos-completo.mp4'
    patch=json.loads((final/'patch.json').read_text())
    assert sha(SOURCE/'rd-documentos-completo.mp4')==patch['source_video_sha256']
    assert sha(movie)==patch['video_sha256']
    assert video_digest(movie)==video_digest(SOURCE/'rd-documentos-completo.mp4')
    assert sha(final/'subtitulos.srt')==sha(SOURCE/'subtitulos.srt')
    assert sha(final/'musica.wav')==sha(SOURCE/'musica.wav')
    dry=read_pcm(final/'narracion.wav');old=read_pcm(SOURCE/'narracion.wav')
    keep=np.ones(len(dry),dtype=bool)
    for c in patch['changes']:
        keep[c['start_sample']:c['end_sample']]=False
        assert c['voice_end']<=c['scene_end']-.25
        assert 'erre de' in c['spoken_text'] and 'RD' in c['display_text']
        assert c['audio_sha256']==sha(REPORT/'audio'/(c['id']+'.wav'))
        expected=np.round(read_pcm(REPORT/'audio'/(c['id']+'.wav'))*c['gain']).astype('<i2')
        assert np.array_equal(expected,dry[c['start_sample']:c['start_sample']+len(expected)])
    assert len(dry)==len(old) and np.array_equal(dry[keep],old[keep])
    assert not np.array_equal(dry,old)
    bed=read_pcm(final/'musica.wav');mixed=read_pcm(final/'mezcla.wav')
    assert np.array_equal(mixed.astype(np.int32),dry.astype(np.int32)+bed.astype(np.int32))
    assert np.max(np.abs(mixed.astype(float)))<.97*32768
    cc=caption_checks(captions(final/'subtitulos.srt'),patch['duration'])
    assert cc['ordered'] and cc['readable']
    with av.open(str(movie)) as c:
        audio=c.streams.audio[0];audio_seconds=float(audio.duration*audio.time_base)
        decoded=np.concatenate([f.to_ndarray().reshape(-1) for f in c.decode(audio=0)])
    assert abs(audio_seconds-patch['duration'])<.025 and np.max(np.abs(decoded))<1
    transcript=json.loads((REPORT/'pronunciation-transcript.json').read_text())
    assert tuple(s['id'] for s in transcript['scenes'])==IDS
    for s in transcript['scenes']:
        assert s['audio_sha256']==sha(final/(s['id']+'-despues.wav'))
        # Whisper may fuse the preceding Spanish "de" into "DRD". Keep the
        # actual transcript as evidence; do not claim phonetic or human review.
        recognized=s['transcript']
        if s['id']=='signature-preview-a':
            recognized=re.sub(r'\bdiseño DRD\b','diseño de RD',recognized,flags=re.I)
        assert re.search(r'\b(?:erre|r)[ .-]*(?:de|d)\b',recognized,re.I), s['transcript']
    facts['rd-pronunciation']=True
    with tempfile.TemporaryDirectory(prefix='rd-pronunciation-check-') as temp:
        temp=Path(temp)
        subprocess.run([sys.executable,str(Path(__file__).with_name('voice.py')),str(REPORT/'voice-recipe.json'),'--output',str(temp/'audio')],check=True)
        cache=json.loads((temp/'audio/narration.json').read_text())
        assert cache['profile']=='voz-1' and cache['network_policy']=='denied'
        assert all(e['cache_hit'] and sha(temp/'audio'/e['deliverable'])==sha(REPORT/'audio'/e['deliverable']) for e in cache['entries'])
        render(temp/'repeat')
        assert sha(temp/'repeat/rd-documentos-completo.mp4')==sha(movie)
    facts['surgical-preservation']=True
    print(json.dumps({'video_identical':True,'music_identical':True,'unchanged_narration_identical':True,'cache_hits':2,'duration':patch['duration'],'decoded_peak':float(np.max(np.abs(decoded))),'transcripts':[s['transcript'] for s in transcript['scenes']],'scope':'local'},ensure_ascii=False))
finally:
    print('NIENFOS_OBSERVATIONS_V1 '+json.dumps({'observations':facts}))
