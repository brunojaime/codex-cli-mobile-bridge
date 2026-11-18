from pathlib import Path
import json,hashlib,os,requests
from dotenv import dotenv_values
root=Path(__file__).resolve().parents[3];out=root/'reports/videos/nienfos-presentacion-v17-locucion-natural';out.mkdir(parents=True,exist_ok=True)
config={**dotenv_values(root/'.env'),**os.environ};key=config.get('ELEVENLABS_API_KEY') or config.get('ELEVEN_LABS_API_KEY')
if not key:raise SystemExit('Falta clave de ElevenLabs en Secrets')
spoken_text='Contanos qué tenés en mente. Nosotros te damos la solución.'
text='Contanos qué tenés en mente. Nosotros <break time="0.22s" /> te damos la solución.'
body={'text':text,'model_id':'eleven_multilingual_v2','voice_settings':{'stability':.55,'similarity_boost':.75,'style':.15,'use_speaker_boost':True,'speed':.97},'seed':42,'previous_text':'Conectamos tus herramientas para simplificar las tareas de cada día.'}
fp=hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest();target=out/'frase-final.mp3';meta=out/'voice-generation.json'
if target.exists() and meta.exists() and json.loads(meta.read_text()).get('fingerprint')==fp:print('CACHE');raise SystemExit()
headers={'xi-api-key':key,'Content-Type':'application/json'}
def usage():
 r=requests.get('https://api.elevenlabs.io/v1/user/subscription',headers=headers,timeout=30)
 return {k:r.json().get(k) for k in ['character_count','character_limit']} if r.ok else None
before=usage()
r=requests.post('https://api.elevenlabs.io/v1/text-to-speech/jIgvw3W75cbd6IP0JYwL',params={'output_format':'mp3_44100_128'},headers=headers,json=body,timeout=100)
if not r.ok:raise SystemExit('Error de generación HTTP '+str(r.status_code))
target.write_bytes(r.content);after=usage();delta=after['character_count']-before['character_count'] if before and after else None
info={'fingerprint':fp,'voice':'Mauricio','text':spoken_text,'synthesis_text':text,'pause_requested_seconds':.22,'speed':.97,'model':body['model_id'],'characters':len(text),'reported_character_cost':r.headers.get('character-cost'),'usage_before':before,'usage_after':after,'usage_delta':delta,'generation_calls':1,'documentation':'https://elevenlabs.io/docs/api-reference/text-to-speech/convert'}
meta.write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n');print(json.dumps(info,ensure_ascii=False))
