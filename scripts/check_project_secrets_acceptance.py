#!/usr/bin/env python3
"""Execute UI/API regressions and CRUD on deployed DEV/PROD using isolated test workspaces."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import dotenv_values  # noqa: E402

REPORT = ROOT / 'reports/secrets-edit-20261001'
BASE = 'https://batata-default-string.tail0302c4.ts.net'
# Reach the actual tailnet origin through the host's existing userspace proxy.
HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({'http': 'http://127.0.0.1:1056', 'https': 'http://127.0.0.1:1056'}))


def request(base, path, method='GET', body=None):
    req = urllib.request.Request(base + path, method=method,
        data=None if body is None else json.dumps(body).encode(),
        headers={'Content-Type': 'application/json'})
    try:
        with HTTP.open(req, timeout=20) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        # Never persist request or response bodies, even on failures.
        return error.code, {}


def target(base):
    status, health = request(base, '/health')
    assert status == 200
    return {'environment': health['environment_identity']['environment'],
            'origin': base, 'release_id': health['backend_commit']}


def deployed_crud(base):
    before = target(base)
    with tempfile.TemporaryDirectory(prefix='secrets-acceptance-', dir=ROOT / '.run') as folder:
        workspace = Path(folder)
        env = workspace / '.env'
        base_body = {'workspace_path': str(workspace)}
        from urllib.parse import urlencode
        query = '?' + urlencode(base_body)
        def call(method, extra):
            return request(base, '/project-secrets', method, {**base_body, **extra})
        values = ['synthetic-one-${KEEP}', 'synthetic-two-with-quotes-and-newline\nend']
        status, created = call('POST', {'name': 'TOKEN', 'value': values[0]})
        assert status == 200 and created['names'] == ['TOKEN']
        assert call('POST', {'name': 'KEEP', 'value': 'synthetic-keep'})[0] == 200
        status, renamed = call('PATCH', {'name': 'TOKEN', 'new_name': 'RENAMED'})
        assert status == 200 and renamed['names'] == ['KEEP', 'RENAMED']
        assert dotenv_values(env, interpolate=False)['RENAMED'] == values[0]
        original = env.read_bytes()
        assert call('PATCH', {'name': 'RENAMED', 'new_name': 'KEEP'})[0] == 409
        assert env.read_bytes() == original
        assert call('PATCH', {'name': 'RENAMED', 'new_name': '9 INVALID', 'value': values[1]})[0] == 422
        status, rotated = call('PATCH', {'name': 'RENAMED', 'new_name': 'FINAL', 'value': values[1]})
        assert status == 200
        assert dotenv_values(env, interpolate=False) == {'FINAL': values[1], 'KEEP': 'synthetic-keep'}
        status, listed = request(base, '/project-secrets' + query)
        assert status == 200 and listed['names'] == ['FINAL', 'KEEP']
        assert not any(value in json.dumps([created, renamed, rotated, listed]) for value in values)
        status, deleted = request(base, '/project-secrets' + query + '&name=FINAL', 'DELETE')
        assert status == 200 and deleted['names'] == ['KEEP']
        assert dotenv_values(env, interpolate=False) == {'KEEP': 'synthetic-keep'}
        assert env.stat().st_mode & 0o777 == 0o600
    after = target(base)
    assert before == after
    return before


def main():
    REPORT.mkdir(parents=True, exist_ok=True)
    observed = {}
    result = {'observations': observed}
    try:
        result['target_before'] = target(BASE + ':8443')
        for label, argv, cwd in [
            ('backend', [str(ROOT / '.venv/bin/python'), '-m', 'pytest', 'tests/test_project_secrets.py', '-q', '--disable-warnings'], ROOT),
            ('frontend', ['/home/batata/.local/bin/flutter', 'test', '--no-pub', 'test/project_secrets_sheet_test.dart'], ROOT / 'frontend/mobile_app'),
        ]:
            test = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=180)
            (REPORT / f'{label}-tests.txt').write_text(test.stdout + test.stderr)
            assert test.returncode == 0, label + ' tests failed'
        targets = {}
        for channel, base in [('prod', BASE), ('dev', BASE + ':8443')]:
            targets[channel] = deployed_crud(base)
        # The Flutter test performs the real widget actions, including Clipboard.setData;
        # deployed API checks prove persistence and names-only responses on each backend.
        for key in ['edit-name', 'copy-name', 'replace-value', 'delete-secret']:
            observed[key] = True
        releases = {}
        for channel, prefix, asset in [('dev', 'android-dev', 'codex-mobile-dev.apk'), ('prod', 'android', 'codex-mobile.apk')]:
            tag = prefix + '-v1.0.0-build.147'
            payload = json.loads(subprocess.check_output(['/usr/bin/gh', 'release', 'view', tag,
                '--repo', 'brunojaime/codex-cli-mobile-bridge', '--json', 'tagName,assets,url'], text=True))
            assert any(item['name'] == asset and item['size'] > 1000000 for item in payload['assets'])
            releases[channel] = {'tag': tag, 'url': payload['url']}
        observed['deploy-evidence'] = True
        result['target_after'] = target(BASE + ':8443')
        assert result['target_before'] == result['target_after']
        result['tested_targets'] = targets
        result['releases'] = releases
        result['limitations'] = 'Widget tests plus live tailnet API tests; no Android-device visual observation or human acceptance.'
        (REPORT / 'executed-evidence.json').write_text(json.dumps(result, indent=2))
        print('NIENFOS_OBSERVATIONS_V1 ' + json.dumps(result))
    except Exception as error:
        result['error'] = type(error).__name__ + ': ' + str(error)
        (REPORT / 'pending-evidence.json').write_text(json.dumps(result, indent=2))
        print('NIENFOS_OBSERVATIONS_V1 ' + json.dumps(result))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
