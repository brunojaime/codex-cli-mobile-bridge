"""One authorized instrumental generation; credentials never leave the environment."""
from pathlib import Path
import os,json,hashlib,sys
import requests
from dotenv import dotenv_values
root=Path(__file__).resolve().parents[3]
out=root/'reports/videos/nienfos-presentacion-v9-musica';out.mkdir(parents=True,exist_ok=True)
c={**dotenv_values(root/'.env'),**os.environ};key=c.get('ELEVENLABS_API_KEY') or c.get('ELEVEN_LABS_API_KEY')
if not key:raise SystemExit('ElevenLabs secret unavailable')
prompt='''An original polished 24.3-second instrumental nu-jazz / jazz-funk track for a modern technology and design studio explainer. Energetic, clever, optimistic, sophisticated and proactive. Approximately 118-120 BPM, a tight lively pocket with subtle sixteenth-note swing. The stars are a beautifully recorded acoustic jazz piano with syncopated extended major ninth and thirteenth chords and short playful melodic answers, plus a clearly audible plucked acoustic upright double bass with a warm woody body, articulate rhythmic walking-and-syncopated phrases and a confident groove. A punchy tasteful acoustic drum kit: firm kick, dry crisp snare, ghost notes, lively controlled hi-hat, a couple of imaginative brief snare rolls and nimble tom fills. Interesting musicianship and rhythmic conversation, not a generic loop. Very subtle modern electronic production accents may support the groove, but keep acoustic piano and upright bass in the foreground. Upbeat and work-in-progress energy, a team solving things together; not sleepy lounge jazz, not a peaceful ballad, not aggressive or chaotic. No horns or saxophone solos. No vocals, no speech, no singing, no scat, no vocal chops. Leave sonic space for a Spanish male narrator and small paper and click sound effects. Start immediately with a compelling piano-and-bass groove and drums, no long intro. Arrangement: 0-4 seconds establish the catchy jazz pocket; 4-13 seconds develop the piano motif with rhythmic chord variations and a short tasteful snare fill; 13-21 seconds increase interplay and energy, let the upright bass move and add one witty compact drum fill around 17 seconds; 21-24.3 seconds land a confident positive piano cadence with the band, leaving a short natural decay for the end card. A complete mini composition with a deliberate ending, not an abruptly cut jam. Entirely instrumental.'''
body={'prompt':prompt,'music_length_ms':24300,'force_instrumental':True,'model_id':'music_v2_5'}
digest=hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest();target=out/'musica-original.mp3';meta=out/'music-generation.json'
if target.exists() and meta.exists() and json.loads(meta.read_text()).get('fingerprint')==digest:
 print('CACHE music',flush=True);sys.exit(0)
r=requests.post('https://api.elevenlabs.io/v1/music',params={'output_format':'mp3_44100_128'},headers={'xi-api-key':key},json=body,timeout=240)
if r.status_code!=200:
 try:
  detail=r.json().get('detail',{});status=detail.get('status','unknown') if isinstance(detail,dict) else 'unknown';message=detail.get('message','') if isinstance(detail,dict) else ''
 except ValueError:status='unknown';message=''
 # Only explicitly selected non-secret provider error fields; no headers or credentials.
 print('API_ERROR',r.status_code,status,message[:400],flush=True)
 meta.write_text(json.dumps({'status':'blocked','http_status':r.status_code,'error_code':status,'message':message[:400],'request':body},ensure_ascii=False,indent=2)+'\n');sys.exit(1)
target.write_bytes(r.content)
meta.write_text(json.dumps({'status':'generated','fingerprint':digest,'request':body,'provider':'ElevenLabs','reported_character_cost':r.headers.get('character-cost'),'song_id':r.headers.get('song-id'),'bytes':len(r.content),'terms_url':'https://elevenlabs.io/music-terms'},ensure_ascii=False,indent=2)+'\n')
print('GENERATED instrumental; cost',r.headers.get('character-cost'),'bytes',len(r.content),flush=True)
