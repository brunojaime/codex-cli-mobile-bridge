"""Exercise inherited tutorial checks and the explicitly selected B delivery."""
from pathlib import Path
import json,subprocess,sys,tempfile
import av
import bookends as b
ROOT=b.ROOT;OUT=ROOT/'reports/rd-video-b-final-20260929';OLD=ROOT/'reports/rd-musica-opciones-20260929/b-teclas'
facts={}
try:
 r=subprocess.run([sys.executable,str(ROOT/'scripts/local_video/check_music_options.py')],capture_output=True,text=True,check=True,timeout=420)
 facts.update(json.loads(next(x.split(' ',1)[1] for x in r.stdout.splitlines() if x.startswith('NIENFOS_OBSERVATIONS_V1 ')))['observations'])
 base=ROOT/'scripts/local_video/skill/local-feature-videos';installed=Path.home()/'.codex/skills/local-feature-videos'
 for rel in ['SKILL.md','music.md','music-preference.json','default-music-plan.json']:assert b.sha(base/rel)==b.sha(installed/rel)
 pref=json.loads((installed/'music-preference.json').read_text());cfg=json.loads((installed/'default-music-plan.json').read_text())
 assert pref['selected_recurring_style']==cfg['mode']=='light-keys'
 assert pref['decision_ref']=='source-29b9f7e55017fc93e90f78f0' and pref['selection_status']=='user_selected'
 assert cfg==json.loads((OLD/'music-plan.json').read_text())
 facts['selected-music-b']=True
 for rel in ['rd-documentos-completo.mp4','mezcla.wav','narracion.wav','musica.wav','subtitulos.srt']:assert b.sha(OUT/rel)==b.sha(OLD/rel),rel
 meta=json.loads((OUT/'music.json').read_text());assert meta['model_api_calls']==meta['tts_calls']==0
 with av.open(str(OUT/'rd-documentos-completo.mp4')) as c:
  frames=sum(1 for _ in c.decode(video=0));assert frames>1100
 with tempfile.TemporaryDirectory(prefix='rd-b-repeat-') as temp:
  subprocess.run([sys.executable,str(ROOT/'scripts/local_video/music.py'),'--source',str(ROOT/'reports/rd-video-editorial-20260929'),'--plan',str(installed/'default-music-plan.json'),'--output',temp],capture_output=True,check=True,timeout=60)
  assert b.sha(Path(temp)/'rd-documentos-completo.mp4')==b.sha(OUT/'rd-documentos-completo.mp4')
 facts['regenerated-video-b']=True
 print(json.dumps({'duration_seconds':meta['duration'],'video_sha256':b.sha(OUT/'rd-documentos-completo.mp4'),'all_frames_decoded':frames,'identical_to_chosen_b':True,'repeated_render_identical':True,'target':str(OUT.relative_to(ROOT))}))
finally:print('NIENFOS_OBSERVATIONS_V1 '+json.dumps({'observations':facts}))
