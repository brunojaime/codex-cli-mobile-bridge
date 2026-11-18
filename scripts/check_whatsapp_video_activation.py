#!/usr/bin/env python3
"""Probe authorized running services. One identified synthetic video per backend.

This does not send WhatsApp messages. Re-runs reuse the recorded session/job;
an uncertain upload is never silently repeated. Model output is not acceptance.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.whatsapp_ingest.worker import encode_multipart_form

OUT = ROOT / 'reports/whatsapp-videos-20261005'
FIXTURE = ROOT / 'tests/fixtures/whatsapp-video.mp4'


def request(origin, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(origin + path, data=data, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def tailnet_json(url):
    return json.loads(subprocess.check_output(['curl', '--fail', '--silent', '--show-error', '--max-time', '30', '--socks5-hostname', '127.0.0.1:1055', url]))


def identity(origin):
    h = request(origin, '/health')
    schema = request(origin, '/openapi.json')['components']['schemas']['ChatMessageAttachmentResponse']
    fingerprint = hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest()[:16]
    env = h['environment_identity']['environment']
    return {'environment': env,
            'origin': 'https://batata-default-string.tail0302c4.ts.net' + (':8443' if env == 'dev' else ''),
            'release_id': h['backend_commit'] + ':video-schema-' + fingerprint}, schema


def probe(env, port):
    origin = f'http://127.0.0.1:{port}'
    before, schema = identity(origin)
    if 'video' not in schema['properties']['kind'].get('enum', []):
        return {'status': 'pending_activation', 'target_before': before}
    path = OUT / f'{env}-probe.json'
    state = json.loads(path.read_text()) if path.exists() else {}
    caption = 'PRUEBA TÉCNICA de adjunto de video. No implementar cambios ni usar herramientas. Responder únicamente: adjunto recibido.'
    if not state.get('session_id'):
        # Use the actual registered Bridge workspace. The test instruction
        # expressly forbids implementation and does not rely on model output.
        workspace = ROOT
        session = request(origin, '/sessions', {'title': f'Prueba técnica video · {env} · 2026-10-05', 'workspace_path': str(workspace)})
        state['session_id'] = session['id']
        save(path, state)
    if not state.get('job_id'):
        if state.get('upload_started'):
            return {'status': 'uncertain_upload_requires_inspection', **state}
        state['upload_started'] = time.time()
        save(path, state)
        boundary = 'whatsapp-video-activation-20261005'
        body = encode_multipart_form(boundary, {'message': caption, 'session_id': state['session_id'], 'codex_options_json': json.dumps({'search_enabled': False})}, [FIXTURE])
        req = urllib.request.Request(origin + '/message/attachments', data=body,
                                     headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
        with urllib.request.urlopen(req, timeout=45) as r:
            accepted = json.load(r)
        state['job_id'] = accepted['job_id']
        save(path, state)
    session = request(origin, '/sessions/' + state['session_id'])
    messages = [m for m in session['messages'] if m['role'] == 'user']
    assert len(messages) == 1 and caption in messages[0]['content']
    attachments = messages[0]['attachments']
    assert len(attachments) == 1 and attachments[0]['kind'] == 'video'
    with urllib.request.urlopen(origin + attachments[0]['download_url'], timeout=30) as r:
        downloaded, mime = r.read(), r.headers['Content-Type']
    assert downloaded == FIXTURE.read_bytes() and mime.startswith('video/mp4')
    # Fetch twice: check persistent API state rather than the upload response.
    again = request(origin, '/sessions/' + state['session_id'])
    assert any(m.get('attachments') == attachments for m in again['messages'])
    after, _ = identity(origin)
    assert before == after
    state.update(status='verified_transport', target_before=before, target_after=after,
                 bytes=len(downloaded), sha256=hashlib.sha256(downloaded).hexdigest(),
                 mime=mime, caption_preserved=True, persistent_download=True,
                 download_url=attachments[0]['download_url'], checked_at=time.time(),
                 boundary='Synthetic API probe; not an incoming WhatsApp message. No model verdict used.')
    save(path, state)
    return state


def main():
    results, observations = {}, {}
    for env, port in [('prod', 8000), ('dev', 8118)]:
        try:
            results[env] = probe(env, port)
        except Exception as e:
            results[env] = {'status': 'error', 'error_type': type(e).__name__}
    try:
        health = request('http://127.0.0.1:8787', '/health')
        units = ['nienfos-whatsapp-ingest.service', 'nienfos-whatsapp-intake-worker.service']
        statuses = {u: subprocess.run(['systemctl', '--user', 'is-active', u], capture_output=True, text=True).stdout.strip() for u in units}
        observations['activate-intake'] = health['connection'] == 'connected' and all(v == 'active' for v in statuses.values())
        results['intake'] = {'connection': health['connection'], 'services': statuses}
    except Exception as e:
        results['intake'] = {'error_type': type(e).__name__}
    if all(results[e].get('status') == 'verified_transport' for e in ['prod', 'dev']):
        observations['activate-bridge'] = True
    releases = {}
    for channel, tag, asset in [('prod', 'android-v1.0.0-build.149', 'codex-mobile.apk'), ('dev', 'android-dev-v1.0.0-build.149', 'codex-mobile-dev.apk')]:
        try:
            release = json.loads(subprocess.check_output(['gh', 'release', 'view', tag, '--json', 'tagName,url,isPrerelease,assets'], cwd=ROOT))
            a = next(a for a in release['assets'] if a['name'] == asset)
            assert a['size'] > 1000000
            public = 'https://batata-default-string.tail0302c4.ts.net' + (':8443' if channel == 'dev' else '')
            updater = tailnet_json(public + f'/app-updates/codex-mobile{"-dev" if channel == "dev" else ""}?platform=android&currentVersion=1.0.0&currentBuild=148&channel={channel}')
            releases[channel] = {'url': release['url'], 'tag': tag, 'asset': a['url'], 'bytes': a['size'], 'updater': {k: updater.get(k) for k in ['latestBuild', 'releaseTag', 'available', 'apkUrl', 'sha256', 'sizeBytes', 'packageId', 'releaseChannel']}}
        except Exception as e:
            releases[channel] = {'status': 'pending', 'error_type': type(e).__name__}
    results['releases'] = releases
    # Updater field names are retained for review; no inferred availability.
    if all('bytes' in releases[c] and releases[c]['updater'].get('latestBuild') == 149 and releases[c]['updater'].get('available') is True for c in ['prod', 'dev']):
        observations['publish-mobile'] = True
    if (OUT / 'activacion.md').exists() and all(results[e].get('status') == 'verified_transport' for e in ['prod', 'dev']):
        observations['activation-evidence'] = True
    payload = {'observations': observations}
    dev = results.get('dev', {})
    if dev.get('target_before') and dev.get('target_after'):
        payload.update(target_before=dev['target_before'], target_after=dev['target_after'])
    save(OUT / 'activation-check.json', {'checked_at': time.time(), 'results': results, **payload})
    print('NIENFOS_OBSERVATIONS_V1 ' + json.dumps(payload))
    return 0 if len(observations) == 4 and all(observations.values()) else 2


if __name__ == '__main__':
    raise SystemExit(main())
