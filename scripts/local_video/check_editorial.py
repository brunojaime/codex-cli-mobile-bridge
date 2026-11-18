"""Check Codex-authored editorial timing against actual rendered media and invalid plans."""
from pathlib import Path
import copy,json,subprocess,sys,tempfile
import av,numpy as np
from PIL import Image
from scipy.signal import correlate
import bookends as b,editorial as e,guide_qc as q,voice
ROOT=b.ROOT;OUT=ROOT/'reports/rd-video-editorial-20260929';BASE=ROOT/'reports/rd-video-guia-20260929';BODY=OUT/'body'
facts={};metrics={}
def fact(k,v):facts[k]=bool(v);assert v,k

def pcm(p):
 r=subprocess.run([b.FF,'-v','error','-i',str(p),'-vn','-ac','1','-ar','8000','-f','f32le','-'],capture_output=True,check=True);return np.frombuffer(r.stdout,dtype='<f4')
def main():
 # Verify retained obligations against the prior real demo, then validate new timing below.
 r=subprocess.run([sys.executable,str(ROOT/'scripts/local_video/check_guide.py')],capture_output=True,text=True,check=True,timeout=180)
 inherited=json.loads(next(x.split(' ',1)[1] for x in r.stdout.splitlines() if x.startswith('NIENFOS_OBSERVATIONS_V1 ')))['observations'];facts.update(inherited)
 brief=e.brief(BASE/'body');stored=json.loads((OUT/'brief.json').read_text());assert brief==stored
 fact('compact-editorial-brief',len((OUT/'brief.json').read_text())<4000 and len(brief['scenes'])==4 and len(brief['silences_over_0_3_seconds'])>0 and all(s['actions'] and s['speech'] for s in brief['scenes']))
 plan=e.load_plan(OUT/'pacing-plan.json',BODY);meta=json.loads((BODY/'render.json').read_text());full=json.loads((OUT/'render.json').read_text());old=json.loads((BASE/'render.json').read_text())
 assert meta['editorial_plan']==plan
 for s in meta['timeline']:
  p=plan['scenes'][s['id']];expected=s['speech_seconds']+p['lead_seconds']+p['tail_seconds']+sum(x['seconds'] for x in p['pauses'])
  assert abs(s['duration']-expected)<=1/60+.001
  assert all(b>a for a,b in zip(s['target_anchors'],s['target_anchors'][1:]))
 new=e.silence_spans(b.read_pcm(OUT/'narracion.wav'));old_sil=e.silence_spans(b.read_pcm(BASE/'narracion.wav'))
 assert max(x['seconds'] for x in new)<max(x['seconds'] for x in old_sil)-1
 # Read actual rendered UI at every action mark; compare to the original local capture.
 r=subprocess.run([b.FF,'-v','error','-i',str(BODY/'rd-documentos.mp4'),'-vf','crop=584:978:68:99,scale=146:245','-pix_fmt','rgb24','-f','rawvideo','-'],capture_output=True,check=True)
 frames=np.frombuffer(r.stdout,dtype=np.uint8).reshape(-1,245,146,3).astype(float);matches=[]
 for cue in meta['cues']:
  wanted=np.asarray(Image.open(BODY/'capture'/cue['scene']/cue['source_frame']).resize((584,978),Image.Resampling.LANCZOS).resize((146,245)),dtype=float)
  indices=range(max(0,int((cue['video_seconds']-.35)*30)),min(len(frames),int((cue['video_seconds']+.35)*30)+1))
  error,index=min((float(np.abs(frames[i]-wanted).mean()),i) for i in indices);assert error<18
  matches.append(abs(index/30-cue['video_seconds']))
 audio=pcm(OUT/'rd-documentos-completo.mp4');audio_errors=[]
 for piece in meta['audio_segments']:
  raw=pcm(BODY/'audio'/f"{piece['id']}.wav");ref=raw[round(piece['source_start_seconds']*8000):round(piece['source_end_seconds']*8000)]
  target=full['body_start']+piece['start_sample']/48000;lo=max(0,round((target-.1)*8000));hi=round((target+.1)*8000)+len(ref)
  found=(lo+int(np.argmax(correlate(audio[lo:hi],ref,mode='valid',method='fft'))))/8000
  assert abs(piece['sample_count']/48000-(piece['source_end_seconds']-piece['source_start_seconds']))<.00005
  audio_errors.append(abs(found-target))
 fact('speech-action-sync',len(matches)==9 and max(matches)<=.35 and max(audio_errors)<.05)
 narration=json.loads((BODY/'audio/narration.json').read_text());same=all(b.sha(BODY/'audio'/x['deliverable'])==x['metadata']['wav_sha256']==b.sha(BASE/'body/audio'/x['deliverable']) for x in narration['entries'])
 old_meta=json.loads((BASE/'body/render.json').read_text());old_pcm=b.read_pcm(BASE/'body/aligned-narration.wav');new_pcm=b.read_pcm(BODY/'aligned-narration.wav')
 for a,z in zip(meta['audio_segments'],old_meta['audio_segments']):
  assert a['sample_count']==z['sample_count']
  assert np.array_equal(new_pcm[a['start_sample']:a['start_sample']+a['sample_count']],old_pcm[z['start_sample']:z['start_sample']+z['sample_count']])
 fact('natural-pauses',same and len(meta['audio_segments'])==9 and max(audio_errors)<.05)
 fact('voice-default',same and voice.profile()[0]=='voz-1' and voice.profile(True)[0]=='peter-fast')
 qc=q.inspect(OUT,write=False);review=json.loads((OUT/'visual-review.json').read_text());assert review['video_sha256']==b.sha(OUT/'rd-documentos-completo.mp4') and review['inspected']
 fact('calm-pace',qc['duration']<old['duration'] and qc['duration']<60 and plan['scenes']['correo']['tail_seconds']>plan['scenes']['abrir']['tail_seconds'])
 fact('guide-readability',qc['captions']['readable'] and qc['captions']['ordered'] and review['captions_legible'])
 fact('complete-bookends',qc['duration']<60 and full['intro_frames']==old['intro_frames'] and full['outro_frames']==old['outro_frames'] and b.sha(OUT/'intro.png')==b.sha(BASE/'intro.png') and b.sha(OUT/'outro.png')==b.sha(BASE/'outro.png'))
 fact('closing-brands',inherited['closing-brands'] and b.sha(OUT/'outro.png')==b.sha(BASE/'outro.png'))
 fact('visible-first-frame',qc['checks']['first_frame_has_title'] and (OUT/'portada.jpg').exists())
 fact('rd-demo-video',inherited['rd-demo-video'] and len(matches)==9)
 fact('fluid-motion',len(frames)>900 and int((np.abs(np.diff(frames,axis=0)).mean(axis=(1,2,3))>.5).sum())>25)
 with tempfile.TemporaryDirectory(prefix='rd-editorial-check-') as temp:
  temp=Path(temp);bad=copy.deepcopy(plan);bad['scenes']['abrir']['lead_seconds']=-1
  variants=[bad,{**plan,'input_digest':'outdated'},{**plan,'scenes':{}},{**plan,'extra':'not allowed'}]
  bad=copy.deepcopy(plan);bad['scenes']['abrir']['pauses'][0]['after_speech_seconds']=.01;variants.append(bad)
  for i,invalid in enumerate(variants):
   path=temp/f'bad-{i}.json';path.write_text(json.dumps(invalid))
   try:e.load_plan(path,BASE/'body')
   except ValueError:pass
   else:raise AssertionError('Invalid plan accepted')
  r=subprocess.run([sys.executable,str(ROOT/'scripts/local_video/run_guided.py'),'--source',str(BASE/'body'),'--pacing-plan',str(temp/'bad-0.json'),'--output',str(temp/'bad-output')],capture_output=True,text=True)
  assert r.returncode!=0 and not (temp/'bad-output').exists()
  fact('codex-pacing-plan',meta['editorial_plan']==plan and len({s['tail_seconds'] for s in plan['scenes'].values()})==4)
  replay=temp/'replay'
  subprocess.run([sys.executable,str(ROOT/'scripts/local_video/run_guided.py'),'--source',str(BASE/'body'),'--pacing-plan',str(OUT/'pacing-plan.json'),'--output',str(replay)],capture_output=True,text=True,check=True,timeout=140)
  run=json.loads((replay/'run.json').read_text());rn=json.loads((replay/'audio/narration.json').read_text())
  assert b.sha(replay/'narracion.wav')==b.sha(OUT/'narracion.wav')
  assert q.inspect(replay,write=False)['checks']==qc['checks']
  fact('reuse-audio',same and run['tts_calls']==0 and all(x['cache_hit'] for x in rn['entries']))
  fact('local-render',inherited['local-render'] and run['model_api_calls']==0)
  metrics['repeat_seconds']=run['seconds']
 skill=Path.home()/'.codex/skills/local-feature-videos';copy_root=ROOT/'scripts/local_video/skill/local-feature-videos'
 for rel in ['SKILL.md','pacing.md','agents/openai.yaml']:assert b.sha(skill/rel)==b.sha(copy_root/rel)
 subprocess.run([str(ROOT/'.venv/bin/python'),str(Path.home()/'.codex/skills/.system/skill-creator/scripts/quick_validate.py'),str(skill)],capture_output=True,check=True)
 fact('future-codex-skill',skill.is_dir() and run['tts_calls']==0 and run['pacing_plan_sha256']==b.sha(OUT/'pacing-plan.json'))
 fact('editorial-video',same and qc['duration']<old['duration']-8 and max(x['seconds'] for x in new)<4 and plan['scenes']['documento']['tail_seconds']>plan['scenes']['abrir']['tail_seconds'])
 fact('automatic-guide-qc',all(qc['checks'].values()) and run['tts_calls']==0)
 fact('evidence-costs',(OUT/'README.md').exists() and 'Codex' in (OUT/'README.md').read_text())
 metrics.update(duration_before=old['duration'],duration_after=qc['duration'],longest_silence_before=max(x['seconds'] for x in old_sil),longest_silence_after=max(x['seconds'] for x in new),brief_characters=len((OUT/'brief.json').read_text()),maximum_audio_error_seconds=max(audio_errors),maximum_action_error_seconds=max(matches),invalid_plans_rejected=len(variants),criteria_passed=sum(facts.values()),target=str((OUT/'rd-documentos-completo.mp4').relative_to(ROOT)))
 print(json.dumps(metrics))
try:main()
finally:print('NIENFOS_OBSERVATIONS_V1 '+json.dumps({'observations':facts}))
