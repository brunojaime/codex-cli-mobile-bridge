"""Resume one blocked Flutter delivery through the DEV coordinator, without models.

This recovery operator publishes only the standard Android DEV tag workflow.
The backend revision is not changed or credited as a mobile release.
"""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.app.application.services.work_coordinator import WorkCoordinator, WorkPolicy


def run(*args):
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--task-id', required=True)
    parser.add_argument('--implementation', type=Path, required=True)
    parser.add_argument('--report-dir', type=Path, required=True)
    args = parser.parse_args()
    args.report_dir.mkdir(parents=True, exist_ok=True)
    version = next(line.split(':', 1)[1].strip() for line in
                   (ROOT / 'frontend/mobile_app/pubspec.yaml').read_text().splitlines()
                   if line.startswith('version:'))
    tag = 'android-dev-v' + version.replace('+', '-build.')
    commit = run('git', 'rev-parse', 'HEAD')
    implementation_commit = run('git', '-C', str(args.implementation), 'rev-parse', 'HEAD')
    assert not run('git', '-C', str(args.implementation), 'status', '--porcelain')
    assert not run('git', 'status', '--porcelain'), 'Release checkout must be clean'
    branch = run('git', 'branch', '--show-current')
    remote = run('git', 'ls-remote', 'origin', 'refs/heads/' + branch).split()
    assert remote and remote[0] == commit, 'Release branch is not confirmed remotely'
    source = 'frontend/mobile_app/lib/src/services/message_outbox.dart'
    assert (ROOT / source).read_bytes() == (args.implementation / source).read_bytes()

    def deliver(task, policy):
        assert task['status'] == 'blocked'
        assert implementation_commit in task['result'] and not task['stop_requested']
        assert policy.dev_branch == 'dev/bridge-bugfixes-20261107'
        assert task['workspace'].endswith('/codex-cli-mobile-bridge')
        existing = run('git', 'ls-remote', 'origin', 'refs/tags/' + tag + '*')
        if not existing:
            subprocess.run(['scripts/publish_android_release.sh', '--channel', 'dev', '--push'],
                           cwd=ROOT, check=True)
        assert run('git', 'ls-remote', 'origin', 'refs/tags/' + tag + '^{}').split()[0] == commit
        deadline = time.monotonic() + 2400
        workflow = None
        while time.monotonic() < deadline:
            runs = json.loads(run('gh', 'run', 'list', '--workflow', 'android-release.yml',
                                 '--commit', commit, '--json',
                                 'databaseId,headSha,headBranch,status,conclusion,url,event'))
            workflow = next((r for r in runs if r['headBranch'] == tag and r['event'] == 'push'), None)
            (args.report_dir / 'workflow.json').write_text(json.dumps(workflow, indent=2) + '\n')
            if workflow and workflow['status'] == 'completed':
                assert workflow['conclusion'] == 'success', 'Android DEV workflow failed'
                break
            time.sleep(15)
        else:
            raise RuntimeError('Android DEV workflow did not finish within 40 minutes')
        release = json.loads(run('gh', 'api', 'repos/brunojaime/codex-cli-mobile-bridge/releases/tags/' + tag))
        assert release['prerelease'] and not release['draft']
        asset = next(a for a in release['assets'] if a['name'] == 'codex-mobile-dev.apk')
        subprocess.run(['gh', 'release', 'download', tag, '--pattern', asset['name'],
                        '--dir', str(args.report_dir), '--clobber'], cwd=ROOT, check=True)
        digest = hashlib.sha256((args.report_dir / asset['name']).read_bytes()).hexdigest()
        assert asset['digest'] == 'sha256:' + digest, 'APK hash differs from GitHub asset'
        build = int(version.split('+')[1])
        updater_url = ('http://127.0.0.1:8118/app-updates/codex-mobile-dev'
                       '?platform=android&currentVersion=1.0.0&currentBuild='
                       + str(build - 1) + '&channel=dev')
        with urlopen(updater_url, timeout=60) as response:
            updater = json.load(response)
        assert updater['available'] and updater['latestBuild'] == build
        assert updater['releaseTag'] == tag and updater['sha256'] == digest
        assert updater['packageId'] == 'io.github.brunojaime.codexmobilebridge.dev'
        (args.report_dir / 'updater.json').write_text(json.dumps(updater, indent=2) + '\n')
        receipt = {'environment': 'dev', 'commit': commit, 'remote_confirmed': True,
                   'delivery_kind': 'android', 'release_tag': tag,
                   'dev_url': release['html_url'], 'verification_url': workflow['url'],
                   'apk_url': asset['browser_download_url'], 'sha256': digest,
                   'implementation_commit': implementation_commit}
        (args.report_dir / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
        return receipt

    coordinator = WorkCoordinator(SimpleNamespace(), args.database, delivery=deliver,
                                  lock_root=Path('/home/batata/Projects/.bridge-work-locks'))
    # The same worker lock prevents a second coordinator from claiming this delivery.
    with args.database.with_suffix('.worker.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with coordinator.ledger() as db:
            task = dict(db.execute('SELECT * FROM work_tasks WHERE id=?', (args.task_id,)).fetchone())
        assert task['status'] == 'blocked', 'Only blocked deliveries can be resumed'
        policy = WorkPolicy.model_validate_json(task['policy'])
        coordinator._complete_delivery((task, policy))
        with coordinator.ledger() as db:
            final = db.execute('SELECT status,problem FROM work_tasks WHERE id=?', (args.task_id,)).fetchone()
        assert final['status'] == 'completed', final['problem']
    print('Android DEV published, updater verified, original backlog task completed')


if __name__ == '__main__':
    main()
