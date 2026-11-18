"""Generate four reusable UI effects with explicit, cached ElevenLabs requests."""
from pathlib import Path
import os,json,hashlib,sys
import requests
from dotenv import dotenv_values
root=Path(__file__).resolve().parents[3]
out=root/'reports/videos/nienfos-presentacion-v6-sonidos';assets=out/'efectos';assets.mkdir(parents=True,exist_ok=True)
c={**dotenv_values(root/'.env'),**os.environ};key=c.get('ELEVENLABS_API_KEY') or c.get('ELEVEN_LABS_API_KEY')
if not key:raise SystemExit('ElevenLabs secret unavailable')
effects=[
 ('barrido','A single very short soft airy whoosh for a refined corporate UI panel sliding horizontally. Subtle dry clean sound, smooth attack and decay, no booming bass, no music, no voice, no background ambience.'),
 ('tarjeta','One single muted soft tactile UI tap, like a small card gently settling into place on a premium digital interface. Short dry rounded pluck, understated, no harsh high frequencies, no music, no voice, no ambience.'),
 ('conexion','One tiny smooth electronic glide for a fine line connecting two interface nodes. Subtle rising airy pulse, restrained and precise, no alarm, no music, no voice, no ambience.'),
 ('confirmacion','One gentle warm two-note confirmation chime for a completed step in a refined corporate interface. Very short soft rounded marimba-like tones, discreet and reassuring, no glitter, no music, no voice, no ambience.')]
summary=[]
for name,prompt in effects:
 body={'text':prompt,'duration_seconds':.5,'prompt_influence':.65,'model_id':'eleven_text_to_sound_v2'}
 digest=hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest();target=assets/(name+'.mp3');meta=assets/(name+'.json')
 if target.exists() and meta.exists() and json.loads(meta.read_text()).get('fingerprint')==digest:
  info=json.loads(meta.read_text());print('CACHE',name,flush=True)
 else:
  r=requests.post('https://api.elevenlabs.io/v1/sound-generation',params={'output_format':'mp3_44100_128'},headers={'xi-api-key':key},json=body,timeout=100)
  if r.status_code!=200:
   try:detail=r.json().get('detail',{});status=detail.get('status','unknown') if isinstance(detail,dict) else 'unknown'
   except ValueError:status='unknown'
   print('API_ERROR',r.status_code,status,flush=True);sys.exit(1)
  target.write_bytes(r.content);info={'fingerprint':digest,'request':body,'reported_character_cost':r.headers.get('character-cost'),'bytes':len(r.content)};meta.write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n');print('GENERATED',name,'cost',info['reported_character_cost'],flush=True)
 summary.append({'name':name,**info})
(out/'effects-generation.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
