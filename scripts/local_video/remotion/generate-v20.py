"""Authorized V20 audio. One continuous take; cache paid requests, no secrets in logs."""
from pathlib import Path
import base64, hashlib, json, math, os, sys
import requests
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'reports/videos/nienfos-v20-crecer'
OUT.mkdir(parents=True, exist_ok=True)
config = {**dotenv_values(ROOT / '.env'), **os.environ}
key = config.get('ELEVENLABS_API_KEY') or config.get('ELEVEN_LABS_API_KEY')
if not key:
    raise SystemExit('Falta credencial de ElevenLabs en Secrets')
headers = {'xi-api-key': key}
text = ('Tu negocio creció. ¿Tu forma de trabajar también? '
        'Mensajes. Planillas. Tareas que se repiten. Y vos, en el medio. '
        'Es hora de dar el próximo paso. '
        'En Nienfos creamos webs y software a medida. '
        'Entendemos tu negocio. Diseñamos con vos. Conectamos tus herramientas. '
        'De una idea, a proyectos reales. '
        'Tu negocio ya está en movimiento. Hagamos que la tecnología lo acompañe. '
        'Nienfos. Hablemos de tu próximo paso.')
voice = 'YLtqUTaEXb7a9MAYuJu4'
body = {'text': text, 'model_id': 'eleven_multilingual_v2', 'seed': 104,
        'voice_settings': {'stability': .38, 'similarity_boost': .75,
                           'style': .25, 'use_speaker_boost': True, 'speed': 1.0}}

def fingerprint(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()

def generate(name, endpoint, request, timed=False):
    meta = OUT / (name + '-generation.json')
    target = OUT / (name + '.mp3')
    fp = fingerprint({'endpoint': endpoint, 'request': request})
    if target.exists() and meta.exists() and json.loads(meta.read_text()).get('fingerprint') == fp:
        print('CACHE', name, flush=True)
        return
    r = requests.post('https://api.elevenlabs.io/v1/' + endpoint,
                      params={'output_format': 'mp3_44100_128'}, headers=headers,
                      json=request, timeout=240)
    if not r.ok:
        raise SystemExit(f'ElevenLabs {name}: HTTP {r.status_code}; no automatic retries')
    if timed:
        result = r.json()
        target.write_bytes(base64.b64decode(result['audio_base64']))
        (OUT / 'alignment.json').write_text(json.dumps(result['normalized_alignment'], ensure_ascii=False, indent=2))
    else:
        target.write_bytes(r.content)
    meta.write_text(json.dumps({'fingerprint': fp, 'provider': 'ElevenLabs',
        'request': request, 'reported_character_cost': r.headers.get('character-cost'),
        'generation_calls': 1, 'voice_name': 'Julieta' if timed else None}, ensure_ascii=False, indent=2))
    print('GENERATED', name, 'reported cost', r.headers.get('character-cost'), flush=True)

generate('locucion', f'text-to-speech/{voice}/with-timestamps', body, timed=True)
a = json.loads((OUT / 'alignment.json').read_text())
aligned = ''.join(a['characters'])
lead = .35
duration = math.ceil((a['character_end_times_seconds'][-1] + lead + 2.0) * 30) / 30
beats = ['Tu negocio creció.', '¿Tu forma', 'Mensajes.', 'Y vos,', 'Es hora',
         'En Nienfos', 'Entendemos', 'Diseñamos', 'Conectamos', 'De una idea,',
         'Tu negocio ya', 'Hagamos', 'Nienfos. Hablemos']
timing = {'duration': duration, 'frames': round(duration*30), 'lead': lead, 'text': text,
          'voice': 'Julieta · una toma continua', 'beats': {}}
for phrase in beats:
    i = aligned.index(phrase)
    timing['beats'][phrase] = round(a['character_start_times_seconds'][i]+lead, 3)
(OUT / 'timing.json').write_text(json.dumps(timing, ensure_ascii=False, indent=2))
public = ROOT / 'scripts/local_video/remotion/public/v20'
public.mkdir(exist_ok=True)
(public / 'timing.json').write_text(json.dumps(timing, ensure_ascii=False, indent=2))
print(json.dumps(timing, ensure_ascii=False), flush=True)
if '--voice-only' in sys.argv:
    raise SystemExit()
prompt = (f'An original {duration:.1f} second instrumental brand film score for a mature Argentine '
          'software and design studio. Confident, crafted, human, memorable. 108 BPM. '
          'A distinctive warm felt-piano three-note motif, deep rounded electric bass, '
          'dry organic drums with subtle syncopation, fine analogue pulse and tactile percussion. '
          'Premium cinematic editorial advertising, restrained musical taste, no stock corporate ukulele. '
          f'First 0-{timing["beats"]["Es hora"]:.1f} seconds: sparse intriguing piano pulse and muted ticking, tension without anxiety. '
          f'At {timing["beats"]["Es hora"]:.1f} seconds, a brief breath and harmonic opening, then a warm confident groove. '
          'Develop the motif with real musical variation, no repetitive generic loop. '
          f'From {timing["beats"]["De una idea,"]:.1f} seconds expand warmly for the real portfolio reveal. '
          f'From {timing["beats"]["Nienfos. Hablemos"]:.1f} seconds resolve to a memorable three-note piano signature '
          'and clean warm final chord, with a natural decay before the end. '
          'Leave the middle frequencies clear for a female Spanish speaking voice. '
          'No singing, no voices, no vocal chops, no epic trailer braams, no EDM drops, no horns.')
generate('musica', 'music', {'prompt': prompt, 'music_length_ms': round(duration*1000),
         'force_instrumental': True, 'model_id': 'music_v2_5'})
