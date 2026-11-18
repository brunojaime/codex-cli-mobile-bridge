"""Generate authorized narration with cached outputs; never serialize credentials."""
from pathlib import Path
import hashlib,json,os,sys
import requests
from dotenv import dotenv_values
root=Path(__file__).resolve().parents[3]
out=root/'reports/videos/nienfos-presentacion-v5-voces';out.mkdir(parents=True,exist_ok=True)
config={**dotenv_values(root/'.env'),**os.environ}
key=config.get('ELEVENLABS_API_KEY') or config.get('ELEVEN_LABS_API_KEY')
if not key:raise SystemExit('ElevenLabs secret unavailable')
voices=[{'id':'ijxn8I4NzJccD2Sa7lcj','name':'Sol','slug':'sol','style':'Argentina · publicidad cálida'}, {'id':'jIgvw3W75cbd6IP0JYwL','name':'Mauricio','slug':'mauricio','style':'Argentina · institucional cercano'}, {'id':'YLtqUTaEXb7a9MAYuJu4','name':'Julieta','slug':'julieta','style':'Argentina · conversacional'}]
texts=['En Nienfos, creamos webs y software a medida.','Entendemos tu negocio para acordar un alcance claro.','Probás el diseño y, con tu devolución, lo mejoramos.','Conectamos tus herramientas para simplificar las tareas de cada día.','Ideas que ya son proyectos reales.','Contanos qué tenés en mente.']
manifest={'provider':'ElevenLabs','model':'eleven_multilingual_v2','subtitle_policy':'none','music':'none','voices':voices,'texts':texts,'usage':[]}
for v in voices:
 folder=out/v['slug'];folder.mkdir(exist_ok=True)
 for i,text in enumerate(texts):
  body={'text':text,'model_id':manifest['model'],'voice_settings':{'stability':.55,'similarity_boost':.75,'style':.15,'use_speaker_boost':True,'speed':1.0},'seed':42}
  if i:body['previous_text']=texts[i-1]
  if i<len(texts)-1:body['next_text']=texts[i+1]
  fingerprint=hashlib.sha256(json.dumps({'voice':v['id'],'body':body},sort_keys=True).encode()).hexdigest()
  target=folder/f'frase-{i+1}.mp3';metadata=folder/f'frase-{i+1}.json'
  if target.exists() and metadata.exists() and json.loads(metadata.read_text()).get('fingerprint')==fingerprint:
   print('CACHE',v['name'],i+1,flush=True);continue
  r=requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{v['id']}",params={'output_format':'mp3_44100_128'},headers={'xi-api-key':key,'Content-Type':'application/json'},json=body,timeout=100)
  if r.status_code!=200:
   try:detail=r.json().get('detail',{});status=detail.get('status','unknown') if isinstance(detail,dict) else 'unknown'
   except ValueError:status='unknown'
   print('API_ERROR',r.status_code,status,flush=True);sys.exit(1)
  target.write_bytes(r.content)
  info={'fingerprint':fingerprint,'text':text,'voice_name':v['name'],'voice_id':v['id'],'model':manifest['model'],'character_cost':r.headers.get('character-cost'),'bytes':len(r.content)}
  metadata.write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n')
  manifest['usage'].append({'voice':v['slug'],'phrase':i+1,'characters':len(text),'reported_character_cost':r.headers.get('character-cost')})
  print('SYNTHESIZED',v['name'],i+1,len(text),'characters',flush=True)
(out/'narration.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print('DONE',flush=True)
