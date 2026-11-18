"""SEA coordinator adapter; official Ed25519 publisher remains the release authority."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import httpx


def main():
    config_path, action = sys.argv[1:]
    assert action in {'inspect', 'validate', 'deploy', 'verify'}
    cfg = json.loads(Path(config_path).read_text())
    root = Path(cfg['root']).resolve()
    canonical = Path(cfg['canonical']).resolve()
    state = Path(cfg['state']).resolve()
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    assert Path.cwd().resolve() == root and root != canonical
    assert cfg['origin'] == 'https://sea-dev.nienfos.workers.dev'
    env = {k: v for k, v in os.environ.items() if k in {'HOME', 'PATH', 'LANG'}}
    env.update(PATH=str(Path(cfg['node']).parent) + ':' + env.get('PATH', ''), CI='true', NODE_OPTIONS='--dns-result-order=ipv4first --no-network-family-autoselection', WRANGLER_SEND_METRICS='false')

    def run(argv, label, timeout=900, secret=False, extra=None):
        result = subprocess.run(argv, cwd=root, env=env | (extra or {}), capture_output=True, timeout=timeout)
        if not secret:
            log = state / (label + '.log')
            log.write_bytes(result.stdout + b'\n' + result.stderr)
            log.chmod(0o600)
        assert result.returncode == 0, label + ' failed; private log retained'
        return result.stdout.decode().strip()

    def git(*args):
        return run(['git', *args], 'git')

    for path, expected in cfg['pinned'].items():
        assert hashlib.sha256((root / path).read_bytes()).hexdigest() == expected, 'Trusted SEA contract changed'
    assert git('branch', '--show-current') == cfg['branch']
    assert git('rev-parse', '--path-format=absolute', '--git-common-dir') == str(canonical / '.git')
    revision = git('rev-parse', 'HEAD')
    # This source-specific check deliberately permits SEA's ignored generated reports.
    run([cfg['node'], '--input-type=module', '-e', "import{sourceIdentity}from'./tools/release-source.mjs';sourceIdentity(process.cwd());"], 'source')
    latest_path = state / 'latest.json'
    latest = json.loads(latest_path.read_text()) if latest_path.exists() else None
    baseline = latest['commit'] if latest else cfg['baseline_revision']
    expected_version = latest['worker_version'] if latest else cfg['baseline_worker']
    assert not git('diff', '--no-renames', '--diff-filter=MD', '--name-only', baseline, '--', 'migrations'), 'Historical migrations changed'
    token = json.loads(run([cfg['node'], 'node_modules/wrangler/bin/wrangler.js', 'auth', 'token', '--json'], 'auth', secret=True))['token']
    client = httpx.Client(headers={'Authorization': 'Bearer ' + token}, timeout=30, follow_redirects=False)
    base = 'https://api.cloudflare.com/client/v4/accounts/c339fa224b83bcca6be83a051720fe70/workers/scripts/sea-dev/'

    def cf(path):
        response = client.get(base + path)
        data = response.json()
        assert response.is_success and data.get('success'), 'Cloudflare read failed'
        return data['result']

    def remote():
        deployment = cf('deployments')['deployments'][0]
        assert len(deployment['versions']) == 1
        version = deployment['versions'][0]['version_id']
        settings, schedules = cf('settings'), cf('schedules')
        assert cf('deployments')['deployments'][0]['versions'] == deployment['versions']
        assert next(b['text'] for b in settings['bindings'] if b['name'] == 'DEPLOYMENT_PROFILE') == 'development'
        return {'version': version, 'bindings': sorted(settings['bindings'], key=lambda b: b['name']), 'crons': sorted(s['cron'] for s in schedules['schedules']), 'compatibility_date': settings['compatibility_date'], 'compatibility_flags': sorted(settings.get('compatibility_flags', []))}

    lock_path = canonical / '.private/releases/publisher.lock'
    with lock_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        before = remote()
        assert action in {'verify','inspect'} or before['version'] == expected_version, 'Remote SEA changed; reconcile rather than overwrite'
        directory = state / revision
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if action == 'inspect':
            print(json.dumps({'environment': 'dev', 'revision': revision, 'baseline_worker': before['version'], 'bindings': len(before['bindings']), 'publication_attempted': False}))
            return
        assess = "import{assessDev}from'./tools/dev-delivery.mjs';const x=assessDev(process.cwd());console.log(JSON.stringify({revision:x.source.revision,artifactDigest:x.receipt.payload.artifactDigest,signatureVerified:true,checks:x.receipt.payload.checks.map(c=>({name:c.name,exit:c.exit}))}));"
        if action == 'validate':
            # Reuse only an artifact that still passes the official signature,
            # source, dependency graph, check and expiry assessment in full.
            try:
                assessed = json.loads(run([cfg['node'], '--input-type=module', '-e', assess], 'official-assessment'))
            except AssertionError:
                run([cfg['node'], 'tools/dev-delivery.mjs'], 'official-prepare')
                assessed = json.loads(run([cfg['node'], '--input-type=module', '-e', assess], 'official-assessment'))
            assert assessed['revision'] == revision and assessed['signatureVerified']
            assert remote() == before, 'Remote SEA changed during preparation'
            (directory / 'validated.json').write_text(json.dumps({'revision': revision, 'artifact_digest': assessed['artifactDigest'], 'before': before, 'checks': assessed['checks']}))
            print(json.dumps({'validated': True, 'revision': revision, 'official_checks': assessed['checks'], 'independent_review_claimed': False}))
            return
        validation = json.loads((directory / 'validated.json').read_text())
        assert validation['revision'] == revision
        assessed = json.loads(run([cfg['node'], '--input-type=module', '-e', assess], 'official-assessment'))
        assert assessed['artifactDigest'] == validation['artifact_digest']
        attempt = directory / 'attempt.json'
        if action == 'deploy':
            assert not git('status', '--porcelain'), 'Coordinator checkout has unrelated changes'
            assert before == validation['before']
            assert git('ls-remote', 'origin', 'refs/heads/' + cfg['branch']).split()[0] == revision
            assert not attempt.exists(), 'Existing attempt requires read-only verification, not redeploy'
            applied = json.loads(run([cfg['node'], 'node_modules/wrangler/bin/wrangler.js', 'd1', 'execute', 'DB', '--remote', '--config', 'wrangler.json', '--command', 'SELECT name FROM d1_migrations ORDER BY name', '--json'], 'migration-history'))[0]['results']
            pending = [p for p in sorted((root / 'migrations').glob('*.sql')) if p.name not in {r['name'] for r in applied}]
            delta = set(git('diff', '--name-only', baseline, '--', 'migrations').splitlines())
            assert all('migrations/' + p.name in delta for p in pending), 'Unreconciled migration history'
            backup = directory / 'immediate-before.sql'
            run([cfg['node'], 'node_modules/wrangler/bin/wrangler.js', 'd1', 'export', 'DB', '--remote', '--config', 'wrangler.json', '--output', str(backup)], 'backup')
            backup.chmod(0o600)
            restored = json.loads(run([cfg['python'], cfg['migration_drill'], str(backup), *map(str, pending)], 'backup-restore'))
            (directory / 'business-baseline.json').write_text(json.dumps(restored['expected_business_counts']))
            assert remote() == before
            attempt.write_text(json.dumps({'state': 'publishing', 'commit': revision}))
            run([cfg['node'], 'tools/deploy-dev.mjs'], 'official-publication')
        # Official readback compares all Worker modules and the expected migration history.
        runtime_dir = directory / 'runtime'
        runtime_dir.mkdir(exist_ok=True, mode=0o700)
        run([cfg['node'], 'tools/verify-dev-runtime.mjs'], 'runtime-readback', extra={'SEA_REPORT_DIR': str(runtime_dir), 'SEA_BUSINESS_BASELINE_FILE': str(directory / 'business-baseline.json')})
        provider = json.loads((runtime_dir / 'provider-after.json').read_text())
        assert provider['completed'] and provider['allModulesVerified'] and provider['exactFrozenWorkerMatch']
        assert provider['sourceRevision'] == revision
        for i in range(8):
            response = httpx.get(cfg['origin'] + '/api/bridge-version', timeout=20)
            if response.status_code == 200 and response.json() == {'environment': 'dev', 'commit': revision}:
                break
            assert i < 7, 'Version endpoint did not converge'
            time.sleep(2)
        after = remote()
        assert after['version'] == provider['active']['versions'][0]['version_id']
        assert {k: v for k, v in after.items() if k != 'version'} == {k: v for k, v in validation['before'].items() if k != 'version'}
        receipt = {'environment': 'dev', 'commit': revision, 'worker_version': after['version'], 'signed_artifact_verified': True, 'worker_modules_verified': True, 'public_commit_verified': True, 'independent_review_claimed': False, 'integral_acceptance': False, 'production_published': False}
        # These are publisher-generated diagnostics, never source/WIP. Preserve
        # their complete evidence privately before restoring the clean checkout.
        for relative in ['reports/implementation-15/official-provenance.json', 'reports/dev-readiness/deploy-attempt.json', 'reports/dev-readiness/release-manifest.json']:
            path = root / relative
            if path.exists():
                saved = directory / 'source-reports' / relative
                saved.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                saved.write_bytes(path.read_bytes()); saved.chmod(0o600)
                if git('ls-files', '--', relative):
                    run(['git', 'restore', '--source=HEAD', '--', relative], 'restore-generated-report')
                else:
                    path.unlink()
        assert not git('status', '--porcelain'), 'Unexpected generated changes require inspection'
        latest_path.write_text(json.dumps(receipt, indent=2) + '\n')
        attempt.write_text(json.dumps(receipt, indent=2) + '\n')
        print(json.dumps(receipt))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('SEA DEV blocked: ' + type(error).__name__ + '; inspect private operator logs.', file=sys.stderr)
        sys.exit(1)
