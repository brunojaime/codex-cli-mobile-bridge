"""Improve an approved tutorial's visual guidance, reusing all captures and speech."""
from pathlib import Path
import argparse,json,shutil,subprocess,sys,time
import voice
import editorial
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--output',type=Path,required=True);p.add_argument('--screen-template',type=Path,default=ROOT/'scripts/local_video/skill/local-feature-videos/default-screen-template.json');p.add_argument('--pacing-plan',type=Path);p.add_argument('--music-plan',type=Path);p.add_argument('--source',type=Path,default=ROOT/'reports/rd-video-local-v3-20260929');a=p.parse_args();out=a.output.resolve()
source=a.source.resolve();body=out/'body';started=time.perf_counter()
if a.pacing_plan:editorial.load_plan(a.pacing_plan,source)
if a.music_plan:
    import music
    music.validate(json.loads(a.music_plan.read_text()))
assert out!=source and body!=source
body.mkdir(parents=True,exist_ok=True)
for folder in ('audio','capture'):shutil.copytree(source/folder,body/folder,dirs_exist_ok=True)
shutil.copyfile(source/'alignment.json',body/'alignment.json')
for e in json.loads((body/'audio/narration.json').read_text())['entries']:
    assert voice.sha(body/'audio'/e['deliverable'])==e['metadata']['wav_sha256']
subprocess.run([sys.executable,str(ROOT/'scripts/local_video/render_v2.py'),'--calm','--guide','--output',str(body)]+(['--pacing-plan',str(a.pacing_plan.resolve())] if a.pacing_plan else []),check=True)
cfg=json.loads((ROOT/'scripts/local_video/rd-bookends.json').read_text());cfg.update(body=str(body),instant_intro=True)
(out/'config.json').write_text(json.dumps(cfg,ensure_ascii=False,indent=2)+'\n')
# This improvement requires only cached narration; fail rather than synthesize unexpectedly.
recipe=ROOT/'reports/rd-video-completo-20260929/bookends-speech.json'
plan=json.loads(subprocess.check_output([sys.executable,str(ROOT/'scripts/local_video/voice.py'),str(recipe),'--output',str(out/'audio'),'--plan'],text=True))
assert all(e['cache_hit'] for e in plan['entries']),'Approved bookend audio missing or corrupted'
subprocess.run([sys.executable,str(ROOT/'scripts/local_video/bookends.py'),'--config',str(out/'config.json'),'--output',str(out)],check=True)
subprocess.run([sys.executable,str(ROOT/'scripts/local_video/guide_qc.py'),str(out)],check=True)
(out/'run.json').write_text(json.dumps({'seconds':time.perf_counter()-started,'tts_calls':0,'model_api_calls':0,'reuse_capture':True,'reuse_audio':True,'pacing_plan_sha256':voice.sha(a.pacing_plan) if a.pacing_plan else None},indent=2)+'\n')

if a.music_plan:
    subprocess.run([sys.executable,str(ROOT/'scripts/local_video/music.py'),'--source',str(out),'--output',str(out/'con-musica'),'--plan',str(a.music_plan.resolve())],check=True)
    run=json.loads((out/'run.json').read_text());run.update(seconds=time.perf_counter()-started,music_plan_sha256=voice.sha(a.music_plan),music_output='con-musica/rd-documentos-completo.mp4');(out/'run.json').write_text(json.dumps(run,indent=2)+'\n')

# The RD adapter declares its own UI geometry; other adapters must supply theirs.
from screen_template import render as compose_screen
screen_plan=json.loads(a.screen_template.read_text())
if screen_plan['client']=='DEMO':screen_plan['client']=cfg['client']
(out/'screen-template-plan.json').write_text(json.dumps(screen_plan,ensure_ascii=False,indent=2)+'\n')
compose_screen(out/'con-musica' if a.music_plan else out,out/'pantalla-grande',out/'screen-template-plan.json',[68,99,584,978])
run=json.loads((out/'run.json').read_text());run.update(final_output='pantalla-grande/rd-documentos-completo.mp4',seconds=time.perf_counter()-started)
(out/'run.json').write_text(json.dumps(run,indent=2)+'\n')
print('Final delivery: '+str(out/'pantalla-grande/rd-documentos-completo.mp4'))
