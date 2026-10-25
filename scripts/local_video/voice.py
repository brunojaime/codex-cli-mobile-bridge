"""Offline narration. Explicit fast mode, content-addressed cache, no automatic fallback."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import sys
import time

ROOT = Path(__file__).resolve().parent
VERSION = 1

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def profile(fast=False):
    settings = json.loads((ROOT / 'voices.json').read_text())
    name = 'peter-fast' if fast else settings['default']
    return name, settings['profiles'][name]

def cache_key(text, config):
    reference_sha = sha(ROOT / config['reference']) if 'reference' in config else None
    payload = {'version': VERSION, 'text': text, 'profile': config, 'reference_sha': reference_sha}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

def cached(cache, key):
    wav, meta = cache / f'{key}.wav', cache / f'{key}.json'
    if not wav.exists() or not meta.exists(): return None
    info = json.loads(meta.read_text())
    return info if info.get('wav_sha256') == sha(wav) else None

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('recipe', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cache', type=Path, default=Path.home()/'.cache/rd-local-video/audio')
    parser.add_argument('--fast', action='store_true', help='Use Peter only when speed was explicitly requested')
    parser.add_argument('--plan', action='store_true', help='Resolve voice/cache without importing a TTS model')
    args = parser.parse_args()
    name, config = profile(args.fast)
    recipe = json.loads(args.recipe.read_text())
    entries = []
    for scene in recipe['scenes']:
        key = cache_key(scene['text'], config)
        info = cached(args.cache, key)
        entries.append({**scene, 'key': key, 'path': str((args.cache/f'{key}.wav').resolve()),
                        'cache_hit': bool(info), 'metadata': info})
    if args.plan:
        print(json.dumps({'profile': name, 'entries': entries}, ensure_ascii=False))
        return
    args.cache.mkdir(parents=True, exist_ok=True)
    args.output.mkdir(parents=True, exist_ok=True)
    # Models and tokenizers must already be installed/downloaded. Fail closed offline.
    os.environ.update(HF_HUB_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1',
                      OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2')
    def deny_network(event, values):
        if event in ('socket.connect', 'socket.getaddrinfo'):
            raise RuntimeError('Narration is offline; network access denied')
    sys.addaudithook(deny_network)
    model = None
    import shutil
    for entry in entries:
        if not entry['cache_hit']:
            import torch
            import numpy as np
            import soundfile as sf
            torch.set_num_threads(2)
            if model is None:
                if config['engine'] == 'chatterbox':
                    from huggingface_hub import snapshot_download
                    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
                    weights = snapshot_download(config['model'], revision=config['revision'], local_files_only=True)
                    model = ChatterboxMultilingualTTS.from_local(weights, 'cpu', t3_model=config['t3_model'])
                    model.prepare_conditionals(str(ROOT/config['reference']), exaggeration=config['exaggeration'])
                else:
                    from pocket_tts import TTSModel
                    model = TTSModel.load_model(language=config['language'])
                    state = model.get_state_for_audio_prompt(config['voice'])
            torch.manual_seed(config['seed'])
            np.random.seed(config['seed'])
            started = time.perf_counter()
            print('Synthesizing '+entry['id']+' with '+name, flush=True)
            if config['engine'] == 'chatterbox':
                audio = model.generate(entry['text'], language_id='es', exaggeration=config['exaggeration'],
                                       cfg_weight=config['cfg_weight'], temperature=config['temperature'])
                sr = model.sr
            else:
                audio = model.generate_audio(state, entry['text'])
                sr = model.sample_rate
            audio = audio.detach().cpu().numpy().flatten()
            if not len(audio) or not np.isfinite(audio).all(): raise RuntimeError('Invalid synthesized audio')
            sf.write(entry['path'], audio, sr, subtype='PCM_16')
            entry['metadata'] = {'seconds': len(audio)/sr, 'sample_rate': sr,
                                 'synthesis_seconds': time.perf_counter()-started,
                                 'wav_sha256': sha(entry['path']), 'text': entry['text'], 'profile': name}
            (args.cache/f"{entry['key']}.json").write_text(json.dumps(entry['metadata'],ensure_ascii=False,indent=2)+'\n')
        destination = args.output/f"{entry['id']}.wav"
        shutil.copyfile(entry['path'], destination)
        entry['deliverable'] = destination.name
        (args.output/'narration.json').write_text(json.dumps({'profile': name, 'network_policy': 'denied',
                    'entries': entries}, ensure_ascii=False, indent=2)+'\n')
        print(entry['id']+': '+('cache hit' if entry['cache_hit'] else 'generated'), flush=True)

if __name__ == '__main__': main()
