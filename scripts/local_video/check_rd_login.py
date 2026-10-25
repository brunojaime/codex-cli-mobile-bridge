"""Executed local acceptance: recovery, account login, media, cache and repeat render."""
from pathlib import Path
import json,subprocess,sys,tempfile
import av,numpy as np
from bookends import ROOT,SR,sha,read_pcm
from rd_login_render import FOLDER,render,validate,paced_voice
from music import render as mix
from guide_qc import inspect,audio_checks
facts={}
try:
    final=FOLDER/'final';movie=final/'rd-documentos-completo.mp4'
    plan=FOLDER/'editorial-plan.json';meta=json.loads((final/'render.json').read_text())
    recipe=json.loads((FOLDER/'voice-recipe.json').read_text());assert meta['video_sha256']==sha(movie)==sha(FOLDER/'rd-ingreso.mp4')
    assert len(recipe['scenes'])==10 and 'independientes' in recipe['scenes'][3]['text']
    assert 'enlace, no una contraseña' in recipe['scenes'][6]['text']
    with tempfile.TemporaryDirectory(prefix='rd-login-check-') as temp:
        temp=Path(temp)
        subprocess.run([sys.executable,str(Path(__file__).with_name('capture_rd_login.py')),'--output',str(temp/'local'),'--port','18924','--offline-provider',str(FOLDER/'capture')],check=True)
        evidence=json.loads((temp/'local/capture/evidence.json').read_text())
        assert evidence['zoho']['actual_start_checked'] and evidence['zoho']['destination']=='https://accounts.zoho.com/oauth/v2/auth'
        assert evidence['provider']['public_page'] and not evidence['provider']['submitted_credentials'] and not evidence['completed_zoho_login']
        provenance=json.loads((FOLDER/'provider-provenance.json').read_text())
        for f,h in provenance['files'].items():assert sha(FOLDER/'capture'/f)==h
        facts['zoho-entry']=True
        recovery=evidence['recovery'];assert recovery['new_password_login'] and recovery['old_password_rejected'] and recovery['one_use_link'] and recovery['mail']['consumed'] and not recovery['mail']['sent_real_mail']
        facts['recovery-flow']=True
        subprocess.run([sys.executable,str(Path(__file__).with_name('voice.py')),str(FOLDER/'voice-recipe.json'),'--output',str(temp/'audio')],check=True)
        cache=json.loads((temp/'audio/narration.json').read_text());assert cache['profile']=='voz-1' and cache['network_policy']=='denied'
        assert len(cache['entries'])==10 and all(e['cache_hit'] and sha(temp/'audio'/e['deliverable'])==sha(FOLDER/'audio'/e['deliverable']) for e in cache['entries'])
        render(FOLDER,temp/'silent',plan);mix(temp/'silent',temp/'repeat',FOLDER/'music-plan.json')
        assert sha(temp/'repeat/rd-documentos-completo.mp4')==sha(movie)
    qc=inspect(final,write=False);assert all(qc['checks'].values())
    with av.open(str(movie)) as c:
        v=c.streams.video[0];a=c.streams.audio[0]
        assert (v.width,v.height)==(720,1280) and float(v.average_rate)==30
        assert abs(float(a.duration*a.time_base)-meta['duration'])<.03
        pcm=np.concatenate([f.to_ndarray().reshape(-1) for f in c.decode(audio=0)])
        assert np.max(np.abs(pcm))<1
    x,y,w,h=meta['ui_rect'];assert w/720>=.95 and w*h/(720*1280)>=.85
    dry=read_pcm(final/'narracion.wav');bed=read_pcm(final/'musica.wav');mixed=read_pcm(final/'mezcla.wav')
    assert np.array_equal(mixed.astype(np.int32),dry.astype(np.int32)+bed.astype(np.int32))
    cfg=json.loads((FOLDER/'music-plan.json').read_text());assert cfg==json.loads((Path(__file__).parent/'skill/local-feature-videos/default-music-plan.json').read_text())
    for s in meta['timeline']:
        voice=paced_voice(FOLDER,s);offset=round(s['voice_start']*SR)
        assert np.array_equal(np.round(voice*s['gain']).astype('<i2'),dry[offset:offset+len(voice)])
        assert s['start']<=s['voice_start']<s['voice_end']<=s['end']
        assert all(s['start']<=a['video_seconds']<=s['end'] for a in s['actions'])
    reset=next(s for s in meta['timeline'] if s['id']=='reset')
    original=read_pcm(FOLDER/'audio/reset.wav');paced=paced_voice(FOLDER,reset);src=dst=0
    for pause in reset['pauses']:
        stop=round(pause['after_seconds']*SR);size=stop-src
        assert np.array_equal(original[src:stop],paced[dst:dst+size]);dst+=size
        count=round(pause['seconds']*SR);assert not np.any(paced[dst:dst+count]);dst+=count;src=stop
    assert np.array_equal(original[src:],paced[dst:])
    visual=json.loads((FOLDER/'visual-review.json').read_text());assert visual['video_sha256']==sha(movie) and visual['observer']=='Codex image viewer' and visual['passed']
    for p,h in visual['frames'].items():assert sha(FOLDER/p)==h
    previous=json.loads((FOLDER/'previous-video.json').read_text());assert sha(ROOT/previous['path'])==previous['sha256']
    facts['login-explanation']=True;facts['approved-login-format']=True
    alignment=json.loads((FOLDER/'alignment.json').read_text())
    assert len(alignment['scenes'])==10
    for s in alignment['scenes']:
        assert s['audio_sha256']==sha(FOLDER/'audio'/f"{s['id']}.wav") and s['script_similarity']>=.7
    bad=json.loads(plan.read_text());bad['scenes'][0]['frames']=2000
    try:validate(bad,FOLDER)
    except ValueError:pass
    else:raise AssertionError('Invalid plan accepted')
    measured=json.loads((FOLDER/'media-qc.json').read_text());assert measured['video_sha256']==sha(movie) and all(s['delta_seconds']<.85 for s in measured['reset_word_action_alignment'])
    facts['local-login-evidence']=True
    print(json.dumps({'target':'isolated RD local + delivered MP4','duration':meta['duration'],'captions':qc['captions'],'cache_hits':10,'deterministic_repeat':True,'real_emails':0,'completed_zoho_login':False,'decoded_peak':float(np.max(np.abs(pcm)))},ensure_ascii=False))
finally:
    print('NIENFOS_OBSERVATIONS_V1 '+json.dumps({'observations':facts}))
