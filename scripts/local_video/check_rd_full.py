"""Execute RD local walkthrough again, replay cache/render, and measure delivered media."""
from pathlib import Path
import copy, json, subprocess, sys, tempfile
import av
import numpy as np
from PIL import ImageFont
from bookends import ROOT, SR, read_pcm, sha
from guide_qc import caption_checks, captions, audio_checks, first_frame_ok
from screen_template import caption_rows, FONT
from rd_full_render import render, validate, DEFAULT_SOURCE, RECIPE
from music import render as mix

REPORT=ROOT/'reports/rd-tutorial-completo-20260930'
FINAL=REPORT/'final'
NODE='/home/batata/.npm/_npx/5705de4b80ce9477/node_modules/node/bin/node'
RD='/home/batata/Projects/rd-gestion-hse/tmp/document-renewal-dev'
MUSIC=ROOT/'scripts/local_video/skill/local-feature-videos/default-music-plan.json'
facts={};metrics={}
try:
    meta=json.loads((FINAL/'render.json').read_text());plan=json.loads((REPORT/'pacing-plan.json').read_text())
    with tempfile.TemporaryDirectory(prefix='rd-full-check-') as temp:
        temp=Path(temp)
        # Exercise the requested product behavior in a fresh isolated synthetic DB.
        subprocess.run([sys.executable,str(ROOT/'scripts/local_video/capture_rd_full.py'),'--rd-project',RD,'--node',NODE,'--output',str(temp/'walkthrough')],check=True)
        fresh=json.loads((temp/'walkthrough/capture/capture.json').read_text())
        captured=json.loads((REPORT/'capture/capture.json').read_text())
        assert fresh['evidence']==captured['evidence']
        sig=fresh['evidence']['signature'];templates=fresh['evidence']['templates']
        assert sig['first_preview']!=sig['second_preview'] and sig['persisted'] and sig['autoNew'] and sig['autoReply']
        facts['signature-walkthrough']=True
        assert all(templates[k] for k in ['existing_updated','new_saved','reloaded','reminder_reviewed','preview_variables_resolved'])
        assert fresh['evidence']['combined']['subject']=='Informe para Empresa DEMO' and fresh['evidence']['combined']['signature']==sig['second_preview']
        facts['template-walkthrough']=True
        # This executes voice.py, whose audit hook denies network. Every phrase must hit verified cache.
        subprocess.run([sys.executable,str(ROOT/'scripts/local_video/run_rd_full.py'),'--folder',str(REPORT),'--output',str(temp/'repeat')],check=True)
        repeated=json.loads((temp/'repeat/audio/narration.json').read_text())
        assert repeated['profile']=='voz-1' and repeated['network_policy']=='denied' and all(e['cache_hit'] for e in repeated['entries'])
        for e in repeated['entries']:assert sha(temp/'repeat/audio'/e['deliverable'])==sha(REPORT/'audio'/e['deliverable'])
        assert sha(temp/'repeat/sin-musica/narracion.wav')==sha(FINAL/'narracion.wav')
        assert sha(temp/'repeat/final/rd-documentos-completo.mp4')==sha(FINAL/'rd-documentos-completo.mp4')
        assert sha(temp/'repeat/final/mezcla.wav')==sha(FINAL/'mezcla.wav')
        metrics['cache_hits']=len(repeated['entries']);metrics['repeat_video_identical']=True
        alignment=json.loads((REPORT/'alignment.json').read_text())
        assert len(alignment['scenes'])==len(repeated['entries'])
        for e in alignment['scenes']:
            assert e['audio_sha256']==sha(REPORT/'audio'/f"{e['id']}.wav")
            assert e['words'] and e['script_similarity']>=.65
        metrics['minimum_local_transcription_similarity']=min(e['script_similarity'] for e in alignment['scenes'])
        rejected=0
        for kind in ('negative','missing','voice-overflow','unauthorized'):
            bad=copy.deepcopy(plan)
            if kind=='negative':bad['scenes'][0]['speech_lead']=-1
            if kind=='missing':bad['scenes'].pop()
            if kind=='voice-overflow':bad['scenes'][0]['frames']=90
            if kind=='unauthorized':bad['long_form_authorized_by']=''
            try:validate(bad,REPORT)
            except ValueError:rejected+=1
        assert rejected==4
        metrics['invalid_plans_rejected']=rejected
        facts['local-reusable-execution']=True
    movie=FINAL/'rd-documentos-completo.mp4'
    with av.open(str(movie)) as c:
        v=c.streams.video[0];duration=float(v.duration*v.time_base)
        assert (v.width,v.height,float(v.average_rate))==(720,1280,30)
        first=next(c.decode(video=0)).to_image();assert first_frame_ok(first)
    assert abs(duration-meta['duration'])<.001 and 60<duration<300
    assert list(meta['chapters'])==['Firma','Plantillas','Novedades']
    assert all(a<b for a,b in zip(meta['chapters'].values(),list(meta['chapters'].values())[1:]))
    assert len(meta['timeline'])==21
    dry=read_pcm(FINAL/'narracion.wav');old=read_pcm(DEFAULT_SOURCE/'narracion.wav')
    offset=round(meta['old_body_start']*SR);old_offset=round(meta['old_source_start']*SR)
    assert np.array_equal(dry[offset:],old[old_offset:])
    assert sha(DEFAULT_SOURCE/'rd-documentos-completo.mp4')==meta['old_source_sha256']
    caps=captions(FINAL/'subtitulos.srt');cc=caption_checks(caps,duration)
    assert cc['ordered'] and cc['readable']
    for c in caps:assert len(caption_rows(c['text'],ImageFont.truetype(FONT,27),684))<=2
    for e in meta['timeline']:
        assert e['start']<=e['voice_start']<e['voice_end']<=e['end']
        assert all(e['start']<=a['video_seconds']<=e['end'] for a in e['actions'])
    facts['complete-three-part-video']=True
    assert meta['ui_rect'][2]/720>=.95 and meta['ui_rect'][2]*meta['ui_rect'][3]/(720*1280)>=.85
    music=json.loads((FINAL/'music.json').read_text());approved=json.loads(MUSIC.read_text())
    assert music['config']==approved
    assert approved['mode']=='light-keys' and approved['level_db_below_voice']==18 and approved['duck_db']==4
    qc=audio_checks(dry);assert qc['valid']
    mixed=read_pcm(FINAL/'mezcla.wav');bed=read_pcm(FINAL/'musica.wav')
    assert len(dry)==len(mixed)==len(bed)==round(duration*SR)
    assert np.array_equal(mixed.astype(np.int32),dry.astype(np.int32)+bed.astype(np.int32))
    assert np.max(np.abs(mixed.astype(float)))/32768<.97
    db=20*np.log10(np.sqrt(np.mean(dry.astype(float)**2))/np.sqrt(np.mean(bed.astype(float)**2)))
    assert db>16
    with av.open(str(movie)) as c:
        stream=c.streams.audio[0];audio_duration=float(stream.duration*stream.time_base)
        decoded=np.concatenate([f.to_ndarray().reshape(-1) for f in c.decode(audio=0)])
    assert abs(audio_duration-duration)<.025 and np.max(np.abs(decoded))<1
    review=json.loads((REPORT/'visual-review.json').read_text())
    assert review['video_sha256']==sha(movie) and review['sheet_sha256']==sha(REPORT/'fotogramas.jpg') and review['result']=='pass'
    assert len(review['inspected_scenes'])>=10
    facts['approved-presentation']=True
    assert fresh['environment']=='local' and fresh['mail_provider']=='simulation' and not fresh['sent_real_mail'] and not fresh['page_errors']
    assert not fresh['evidence']['combined']['sent']
    metrics.update(duration=duration,caption_checks=cc,dry_audio_checks=qc,music_below_voice_rms_db=float(db),decoded_peak=float(np.max(np.abs(decoded))),audio_duration=audio_duration,video_sha256=sha(movie),source_preserved=True)
    facts['full-tutorial-evidence']=True
    print(json.dumps(metrics))
finally:
    print('NIENFOS_OBSERVATIONS_V1 '+json.dumps({'observations':facts}))
