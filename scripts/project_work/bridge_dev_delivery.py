"""Publish tested Bridge backend bugfixes to DEV after its accepted jobs drain."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import sqlite3

import httpx


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def run(argv, cwd, **kwargs):
    r = subprocess.run(argv, cwd=cwd, capture_output=True, **kwargs)
    if r.returncode:
        raise RuntimeError('Operator command failed: ' + Path(argv[0]).name)
    return r.stdout.decode().strip()


def prepare(config, bootstrap=False):
    checkout, runtime, state = (Path(config[k]) for k in ['checkout', 'runtime', 'state'])
    assert run(['git', 'branch', '--show-current'], checkout) == config['branch']
    assert not run(['git', 'status', '--porcelain'], checkout)
    revision = run(['git', 'rev-parse', 'HEAD'], checkout)
    stage = state / revision / 'files'
    stage.mkdir(parents=True, exist_ok=True)
    if bootstrap:
        paths = ['backend/app/application/services/' + f for f in [
            'session_file_service.py', 'backend_automation_release.py', 'work_coordinator.py', 'work_settings.py', 'message_service.py', 'feedback_queue_service.py']]
        paths.extend(['backend/app/api/routes.py', 'backend/app/api/work_routes.py'])
    else:
        paths = run(['git', 'diff', '--name-only', config['deployed_commit'], revision], checkout).splitlines()
        paths = [p for p in paths if p.startswith('backend/')]
    assert paths and all(p.startswith('backend/') and p.endswith('.py') and '..' not in Path(p).parts for p in paths)
    files = {}
    for relative in paths:
        destination, source, candidate = runtime / relative, checkout / relative, stage / relative
        candidate.parent.mkdir(parents=True, exist_ok=True)
        before = destination.read_bytes() if destination.exists() else None
        if bootstrap:
            assert digest(destination) == config['bootstrap_before'][relative], 'DEV changed since preparation; reconcile before bootstrap'
            after = source.read_bytes()
            if relative.endswith('/message_service.py'):
                text = before.decode()
                needle = 'workdir=session.workspace_path,'
                assert needle in text
                after = text.replace(needle, 'workdir=(self._work_coordinator.execution_workspace_for(session) if getattr(self, "_work_coordinator", None) is not None else session.workspace_path),').encode()
            elif relative.endswith('/api/routes.py'):
                text = before.decode()
                needle = '@router.get("/health", response_model=HealthResponse)'
                branch = source.read_text()
                addition = branch[branch.index('from backend.app.application.services.backend_automation_release import'):branch.index(needle)]
                assert text.count(needle) == 1
                after = text.replace(needle, addition + needle).encode()
            candidate.write_bytes(after)
        else:
            if before is not None:
                candidate.write_bytes(before)
            patch = subprocess.check_output(['git', 'diff', '--binary', config['deployed_commit'], revision, '--', relative], cwd=checkout)
            run(['patch', '--batch', '--forward', '--fuzz=0', '-p1', '-d', str(stage)], checkout, input=patch)
        files[relative] = {'before': hashlib.sha256(before).hexdigest() if before is not None else None, 'after': digest(candidate)}
    env = dict(os.environ, PYTHONPATH=str(checkout))
    run([sys.executable, '-m', 'pytest', 'tests/test_session_files.py', 'tests/test_backend_automation_release.py', '-q', '--disable-warnings'], checkout, env=env, timeout=180)
    plan = {'revision': revision, 'stage': str(stage), 'runtime': str(runtime), 'files': files, 'bootstrap': bootstrap}
    path = state / revision / 'plan.json'
    write(path, plan)
    return path


def activate(config_path, plan_path):
    config = json.loads(config_path.read_text())
    plan = json.loads(plan_path.read_text())
    runtime, stage = Path(plan['runtime']), Path(plan['stage'])
    report = Path(config['report'])
    with httpx.Client(base_url='http://127.0.0.1:8118', trust_env=False, timeout=30) as client:
        while True:
            health = client.get('/health').raise_for_status().json()
            assert health['environment_identity']['environment'] == 'dev'
            status = client.get('/maintenance/drain').raise_for_status().json()
            write(report, {'state': 'waiting_for_idle', 'commit': plan['revision'], 'active_jobs': status['active_job_count'], 'in_flight_messages': status['in_flight_message_count']})
            if not status['requested'] and not any(status[k] for k in ['active_job_count', 'active_session_count', 'in_flight_message_count']):
                break
            time.sleep(15)
        assert str(runtime / 'main.py') in run(['systemctl', '--user', 'show', 'codex-mobile-bridge-dev.service', '-p', 'ExecStart', '--value'], runtime)
        for relative, hashes in plan['files'].items():
            assert digest(runtime / relative) == hashes['before'], 'DEV source changed; reconcile instead of overwriting'
            assert digest(stage / relative) == hashes['after']
        remote = run(['git', 'ls-remote', 'origin', 'refs/heads/' + config['branch']], Path(config['checkout'])).split()
        assert remote and remote[0] == plan['revision']
        drain = client.post('/maintenance/drain', json={'requested': True}).raise_for_status().json()
        if not drain['ready_to_restart']:
            client.post('/maintenance/drain', json={'requested': False}).raise_for_status()
            return activate(config_path, plan_path)
        applied = []
        behavior_verified = False
        manifest = runtime / '.run/bridge-autofix/loaded-release.json'
        old_manifest = manifest.read_bytes() if manifest.exists() else None
        try:
            for relative in plan['files']:
                destination = runtime / relative
                if destination.exists():
                    backup = plan_path.parent / 'originals' / relative
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    backup.write_bytes(destination.read_bytes())
                destination.parent.mkdir(parents=True, exist_ok=True)
                temporary = destination.with_suffix('.automation-tmp')
                temporary.write_bytes((stage / relative).read_bytes())
                temporary.replace(destination)
                applied.append(relative)
            write(manifest, {'commit': plan['revision']})
            write(report, {'state': 'restarting_idle_dev', 'commit': plan['revision']})
            run(['systemctl', '--user', 'restart', 'codex-mobile-bridge-dev.service'], runtime, timeout=90)
            for _ in range(60):
                try:
                    receipt = client.get('/automation/version').raise_for_status().json()
                    if receipt == {'environment': 'dev', 'commit': plan['revision']}:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(1)
            else:
                raise RuntimeError('DEV revision was not confirmed')
            # Confirm the actual behavior using a real session, without running a model.
            session = config['verification_session']
            for endpoint in ['files', 'files/content']:
                for parameter in ['path', 'relative_to']:
                    params = {'path': 'AGENTS.md', parameter: 'file://[broken/report.md'}
                    assert client.get(f'/sessions/{session}/{endpoint}', params=params).status_code == 422
            assert client.get(f'/sessions/{session}/files', params={'path': 'AGENTS.md'}).status_code == 200
            behavior_verified = True
            config['deployed_commit'] = plan['revision']
            write(config_path, config)
            if plan['bootstrap']:
                policy = json.loads(Path(config['policy_file']).read_text())
                client.put('/work/policy', json=policy).raise_for_status()
                client.put('/work/settings', json={'workspace_path': policy['workspace_path'], 'settings': {'automatic_execution': True}}).raise_for_status()
            # Preserve the existing backlog identities when a restarted backend
            # cannot return to its old delivery thread.
            checkout = Path(config['checkout'])
            receipt = {'environment': 'dev', 'commit': plan['revision'], 'remote_confirmed': True,
                       'dev_url': config['dev_url'], 'verification_url': config['dev_url'] + '/automation/version'}
            for database, task_id in [(config['dev_database'], None), (config['primary_database'], config['initial_task_id'] if plan['bootstrap'] else '')]:
                if task_id == '':
                    continue
                with sqlite3.connect(database, timeout=30) as db:
                    rows = db.execute('SELECT id,status,policy,base_commit FROM work_tasks WHERE workspace=?', (config['workspace'],)).fetchall()
                    for ident, status, snapshot, base in rows:
                        initial = bool(task_id and ident == task_id and status in {'queued','blocked','cancelled'})
                        native = not task_id and status in {'delivering','blocked'} and snapshot and json.loads(snapshot).get('dev_branch') == config['branch'] and base != plan['revision']
                        if not (initial or native):
                            continue
                        db.execute("UPDATE work_tasks SET status='completed',problem=NULL,receipt=?,result=CASE WHEN result='' THEN ? ELSE result END,updated_at=? WHERE id=?", (json.dumps(receipt), 'Corrección del visor validada y publicada exclusivamente en DEV; recibo y versión comprobados.', __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(), ident))
                        db.execute("INSERT INTO work_events(task_id,kind,text,created_at) VALUES (?,?,?,?)", (ident, 'completed', 'Entrega DEV comprobada tras activación segura', __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()))
            if plan['bootstrap']:
                # Expose the completed first fix in DEV as history, without
                # creating or executing a duplicate task.
                with sqlite3.connect(config['primary_database']) as source, sqlite3.connect(config['dev_database'], timeout=30) as target:
                    source.row_factory = sqlite3.Row
                    row = source.execute('SELECT * FROM work_tasks WHERE id=?', (config['initial_task_id'],)).fetchone()
                    if row and row['status'] == 'completed':
                        columns = [r[1] for r in target.execute('PRAGMA table_info(work_tasks)') if r[1] in row.keys()]
                        target.execute('INSERT OR IGNORE INTO work_tasks (' + ','.join(columns) + ') VALUES (' + ','.join('?' for _ in columns) + ')', [row[k] for k in columns])
            write(report, {'state': 'published_and_verified', 'commit': plan['revision'], 'environment': 'dev', 'malformed_references': 422, 'valid_reference': 200, 'automation_policy_loaded': True})
        except Exception:
            if applied and not behavior_verified:
                # If the new process accepted work, let it finish before rollback.
                while True:
                    try:
                        status = client.get('/maintenance/drain').raise_for_status().json()
                        if any(status[k] for k in ['active_job_count', 'active_session_count', 'in_flight_message_count']):
                            time.sleep(15)
                            continue
                        drained = client.post('/maintenance/drain', json={'requested': True}).raise_for_status().json()
                        if not drained['ready_to_restart']:
                            time.sleep(15)
                            continue
                    except httpx.HTTPError:
                        pass  # A process which failed to start cannot have accepted work.
                    break
                for relative in applied:
                    assert digest(runtime / relative) == plan['files'][relative]['after'], 'Concurrent change prevents automatic rollback'
                    backup = plan_path.parent / 'originals' / relative
                    if backup.exists():
                        (runtime / relative).write_bytes(backup.read_bytes())
                    else:
                        (runtime / relative).unlink(missing_ok=True)
                if old_manifest is None:
                    manifest.unlink(missing_ok=True)
                else:
                    manifest.write_bytes(old_manifest)
                run(['systemctl', '--user', 'restart', 'codex-mobile-bridge-dev.service'], runtime, timeout=90)
            raise
        finally:
            try:
                client.post('/maintenance/drain', json={'requested': False}).raise_for_status()
            except httpx.HTTPError:
                pass


def main():
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['validate', 'deploy', 'activate', 'bootstrap'])
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--plan', type=Path)
    args = p.parse_args()
    config = json.loads(args.config.read_text())
    if args.action == 'activate':
        try:
            activate(args.config, args.plan)
        except Exception as error:
            write(Path(config['report']), {'state': 'blocked_requires_inspection', 'error': type(error).__name__})
            raise SystemExit(1)
        return
    plan = prepare(config, bootstrap=args.action == 'bootstrap')
    if args.action == 'validate':
        return
    # Separate cgroup: a DEV backend restart must not kill its own activator.
    unit = 'bridge-autofix-' + json.loads(plan.read_text())['revision'][:12]
    run(['systemd-run', '--user', '--collect', '--unit=' + unit, sys.executable, str(Path(__file__).resolve()), 'activate', '--config', str(args.config.resolve()), '--plan', str(plan)], Path(config['checkout']))
    if args.action == 'deploy':
        while True:
            time.sleep(5)  # Native delivery persists through restart and reconciles the receipt.


if __name__ == '__main__':
    main()
