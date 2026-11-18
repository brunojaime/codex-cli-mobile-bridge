"""Generate ten context-specific effects with explicit, cached ElevenLabs requests."""
from pathlib import Path
import os,json,hashlib,sys
import requests
from dotenv import dotenv_values
root=Path(__file__).resolve().parents[3]
out=root/'reports/videos/nienfos-presentacion-v7-paleta-sonora';assets=out/'efectos';assets.mkdir(parents=True,exist_ok=True)
c={**dotenv_values(root/'.env'),**os.environ};key=c.get('ELEVENLABS_API_KEY') or c.get('ELEVEN_LABS_API_KEY')
if not key:raise SystemExit('ElevenLabs secret unavailable')
effects=[
 ('transicion_aire',.8,'One smooth lateral air sweep for a minimal corporate scene transition. A broad soft textured whoosh moving left to right, with a rounded low-mid body and a soft natural decay. Not a beep, not a whistle. Isolated sound effect, no music, no voice.'),
 ('papel_desliza',.8,'Single close-up foley of one thick paper card sliding gently across a clean wooden desk and stopping. Soft dry paper friction followed by a very light contact. Tactile and realistic, not electronic. Isolated sound effect, no voice, no music.'),
 ('tarjeta_apoya',.6,'One soft dry rounded tap of thick cardstock being set down on a wooden desk. A compact warm contact with a tiny paper rustle. Natural material sound, not a digital beep, no ringing. Single isolated foley effect, no voice, no music.'),
 ('trazo_diseno',.9,'One short continuous confident pencil stroke on textured paper, a smooth close-up graphite scratch that starts gently and ends cleanly. Represents drawing a simple design line. No tapping, no electronic tones. Single isolated foley, no voice, no music.'),
 ('revision_pagina',.8,'One small paper page gently flipping over and landing, a light dry flutter and soft paper contact. For reviewing and updating a design. Natural realistic paper foley, not a swoosh beep. No music, no voice.'),
 ('linea_conecta',.65,'Single soft narrow brushed-air zipper gesture, a fine tactile line being traced downward and joining at the end with a subtle dry tick. Quiet precise sound for a diagram connector. No musical pitch, no bell, no voice, no music.'),
 ('datos_circulan',.9,'A single short delicate burst of three distinct soft granular digital data pulses flowing into each other. Warm filtered electronic texture with tiny stereo movement, restrained technological sound. No notification beep, no melody, no voice, no music.'),
 ('conexion_encaja',.6,'One small precision connector gently clicking into its socket, a tiny sliding mechanical contact followed by a satisfying low soft snap. Clean dry close-up foley, not metallic, not a bell, not an alarm. Isolated effect, no voice, no music.'),
 ('proyecto_revela',.8,'One smooth soft glass panel sliding open into position with a light airy friction and a tiny muted landing. Elegant clean display reveal, distinct from paper. No shattering, no high pitched ringing, no musical tone, no voice, no music.'),
 ('cierre_marca',1.0,'A single restrained warm airy brand reveal accent: gentle low soft swell with a fine breathy texture, settling into silence. Refined corporate end-card feeling, no impact boom, no bells, no arpeggio, no melody, no music, no voice.')]
summary=[]
for name,duration,prompt in effects:
 body={'text':prompt,'duration_seconds':duration,'prompt_influence':.65,'model_id':'eleven_text_to_sound_v2'}
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
