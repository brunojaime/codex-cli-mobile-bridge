"""Reference-guided musical variation plus two clean UI effects; cache every paid call."""
from pathlib import Path
import os,json,hashlib,sys,datetime
import requests
from dotenv import dotenv_values
root=Path(__file__).resolve().parents[3];out=root/'reports/videos/nienfos-presentacion-v10-groove';out.mkdir(parents=True,exist_ok=True)
c={**dotenv_values(root/'.env'),**os.environ};key=c.get('ELEVENLABS_API_KEY') or c.get('ELEVEN_LABS_API_KEY')
if not key:raise SystemExit('ElevenLabs secret unavailable')
headers={'xi-api-key':key}
def fail(r,stage):
 try:d=r.json().get('detail',{});code=d.get('status','unknown') if isinstance(d,dict) else 'unknown';message=d.get('message','') if isinstance(d,dict) else ''
 except ValueError:code='unknown';message=''
 
 if isinstance(d,list):
  errors=[{'loc':x.get('loc'),'msg':x.get('msg'),'type':x.get('type')} for x in d]
  (out/'api-validation-error.json').write_text(json.dumps(errors,indent=2)+'\n');print(json.dumps(errors),flush=True)
 print('API_ERROR',stage,r.status_code,code,message[:200],flush=True);sys.exit(1)
def usage():
 params={'start_unix':int(datetime.datetime(2026,11,4,tzinfo=datetime.timezone.utc).timestamp()*1000),'end_unix':int(datetime.datetime.now(datetime.timezone.utc).timestamp()*1000),'breakdown_type':'product_type','metric':'credits'}
 r=requests.get('https://api.elevenlabs.io/v1/usage/character-stats',params=params,headers=headers,timeout=35)
 return r.json() if r.status_code==200 else {'http_status':r.status_code}
if not (out/'usage-before.json').exists():(out/'usage-before.json').write_text(json.dumps(usage(),indent=2)+'\n')
# Store the user's previously generated instrumental for conditional generation.
upload_meta=out/'reference-upload.json'
if upload_meta.exists():ref=json.loads(upload_meta.read_text())
else:
 with (root/'reports/videos/nienfos-presentacion-v9-musica/musica-original.mp3').open('rb') as file:
  r=requests.post('https://api.elevenlabs.io/v1/music/upload',headers=headers,files={'file':('nienfos-jazz-original.mp3',file,'audio/mpeg')},data={'extract_composition_plan':'false'},timeout=180)
 if r.status_code!=200:fail(r,'upload-reference')
 ref={'song_id':r.json()['song_id'],'reported_character_cost':r.headers.get('character-cost'),'source':'../nienfos-presentacion-v9-musica/musica-original.mp3'};upload_meta.write_text(json.dumps(ref,indent=2)+'\n');print('STORED musical reference',flush=True)
styles=['instrumental acoustic nu-jazz and jazz-funk','same bright sophisticated acoustic jazz piano character and harmonic vocabulary as the reference','118-120 BPM with a lively swung sixteenth-note pocket','more adventurous syncopated piano comping and short playful melodic replies','upright acoustic double bass prominently upfront, as audible as the piano, warm woody low-mid body and articulate walking runs','punchier more prominent acoustic drum kit with firm kick, crisp dry snare backbeat, lively hi-hat, ghost notes','compact surprising snare rolls and nimble tom fills around 7, 14 and 18 seconds','the trio talks rhythmically to each other','optimistic, proactive modern technology studio identity','subtle electronic production accents only','clean natural positive final piano cadence with bass and drums, short decay','leave room for male Spanish narration']
chunk={'text':'[Instrumental jazz-funk variation]','duration_ms':24300,'positive_styles':styles,'negative_styles':['vocals','singing','speech','scat','vocal chops','sleepy lounge jazz','ambient slow intro','harsh industrial sounds','zipper scraping sound effects','horn or saxophone solos','aggressive EDM drop','busy uninterrupted drum solo'],'context_adherence':'high','conditioning_ref':{'song_id':ref['song_id'],'range':{'start_ms':0,'end_ms':24300}},'condition_strength':'high'}
body={'composition_plan':{'chunks':[chunk]},'model_id':'music_v2_5','store_for_inpainting':True}
digest=hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest();target=out/'musica-original.mp3';meta=out/'music-generation.json'
if not (target.exists() and meta.exists() and json.loads(meta.read_text()).get('fingerprint')==digest):
 r=requests.post('https://api.elevenlabs.io/v1/music',params={'output_format':'mp3_44100_128'},headers=headers,json=body,timeout=240)
 if r.status_code!=200:fail(r,'conditioned-music')
 target.write_bytes(r.content);meta.write_text(json.dumps({'status':'generated','fingerprint':digest,'request':body,'provider':'ElevenLabs','reported_character_cost':r.headers.get('character-cost'),'song_id':r.headers.get('song-id'),'reference_guided':True,'terms_url':'https://elevenlabs.io/music-terms'},ensure_ascii=False,indent=2)+'\n');print('GENERATED reference-guided variation',flush=True)
assets=out/'efectos';assets.mkdir(exist_ok=True)
effects=[('tarjeta_limpia',.5,'One single tiny soft rounded dry tactile tick for a digital card finishing its entrance. A gentle fingertip touching thick matte card, short muted contact with a little air. Precise quiet clean UI sound. No friction, no sliding, no zipper, no ratchet, no spring, no scraping, no metallic sound, no music, no voice.'),('hoja_fina',.6,'One short gentle flutter of a thin paper sheet being lifted and placed down, a delicate soft airy flap followed by a muted tap. Close-up natural paper sound, elegant and light. No long rubbing, no scraping, no zipper, no fabric, no metallic texture, no electronic tone, no music, no voice.')]
summary=[]
for name,length,prompt in effects:
 body={'text':prompt,'duration_seconds':length,'prompt_influence':.75,'model_id':'eleven_text_to_sound_v2'};digest=hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest();a=assets/(name+'.mp3');m=assets/(name+'.json')
 if not (a.exists() and m.exists() and json.loads(m.read_text()).get('fingerprint')==digest):
  r=requests.post('https://api.elevenlabs.io/v1/sound-generation',params={'output_format':'mp3_44100_128'},headers=headers,json=body,timeout=100)
  if r.status_code!=200:fail(r,name)
  a.write_bytes(r.content);m.write_text(json.dumps({'fingerprint':digest,'request':body,'reported_character_cost':r.headers.get('character-cost')},ensure_ascii=False,indent=2)+'\n');print('GENERATED effect',name,flush=True)
 summary.append({'name':name,**json.loads(m.read_text())})
# Reuse only the short click the user explicitly liked.
import shutil
shutil.copy2(root/'reports/videos/nienfos-presentacion-v8-papel-clicks/efectos/conexion_encaja.mp3',assets/'conexion_encaja.mp3')
summary.append({'name':'conexion_encaja','reused_from':'nienfos-presentacion-v8-papel-clicks','reported_character_cost':'0'})
(out/'effects-generation.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
(out/'usage-after.json').write_text(json.dumps(usage(),indent=2)+'\n')
print('DONE',flush=True)
