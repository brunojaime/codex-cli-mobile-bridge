"""Finish DEV-to-PROD routing once the current accepted conversation is idle."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time
from contextlib import ExitStack
import httpx
from scripts.sync_terminal_session import sync_terminal_session

ROOT=Path('/home/batata/Projects/codex-cli-mobile-bridge')
STATE=ROOT/'.run/centralize-prod-20261109'
REPORT=ROOT/'reports/project-automation/coordinator-owner-20261109/routing.json'
SESSION='74b99550-a0d4-474e-b2d9-633570ae796c'
SOURCE=ROOT/'.run/dev-backend-8118/data/chat_store.sqlite3'
TARGET=ROOT/'.data/chat_store.sqlite3'


def save(state,**extra):
    temporary=REPORT.with_suffix('.tmp')
    temporary.write_text(json.dumps({'state':state,**extra},indent=2)+'\n');temporary.replace(REPORT)


def main():
    plan=json.loads((STATE/'runtime-plan.json').read_text());runtime=Path(plan['runtime']);stage=Path(plan['stage'])
    deadline=time.monotonic()+21600
    with httpx.Client(base_url='http://127.0.0.1:8118',timeout=180,trust_env=False) as client:
        while time.monotonic()<deadline:
            with sqlite3.connect(SOURCE, timeout=10) as check:
                current=check.execute('SELECT active_agent_run_id FROM sessions WHERE id=?',(SESSION,)).fetchone()
            if current and current[0]:
                save('waiting_for_current_chat_to_finish',active_jobs=1);time.sleep(5);continue
            try:
                status=client.get('/maintenance/drain').raise_for_status().json()
            except httpx.TimeoutException:
                save('waiting_for_drain_check');time.sleep(30);continue
            if status['requested']:
                save('waiting_for_existing_maintenance');time.sleep(15);continue
            if any(status[k] for k in ('active_job_count','active_session_count','in_flight_message_count')):
                save('waiting_for_current_chat_to_finish',active_jobs=status['active_job_count']);time.sleep(5);continue
            for relative,pins in plan['files'].items():
                assert hashlib.sha256((runtime/relative).read_bytes()).hexdigest() in (pins['before'],pins['after']),'Runtime changed; do not overwrite'
                assert hashlib.sha256((stage/relative).read_bytes()).hexdigest()==pins['after'],'Candidate changed'
            status=client.post('/maintenance/drain',json={'requested':True}).raise_for_status().json()
            if not status['ready_to_restart']:
                client.post('/maintenance/drain',json={'requested':False}).raise_for_status()
                time.sleep(5)
                continue
            break
        else:raise TimeoutError('Accepted work did not become idle')
        try:
            # Current conversation is copied only after its final response is durable.
            with sqlite3.connect(SOURCE,timeout=30) as source,sqlite3.connect(TARGET,timeout=30) as target:
                assert not source.execute("SELECT 1 FROM jobs WHERE session_id=? AND status NOT IN ('completed','failed','cancelled')",(SESSION,)).fetchone()
                assert source.execute('SELECT active_agent_run_id FROM sessions WHERE id=?',(SESSION,)).fetchone()==(None,)
                backup=STATE/'prod-chat-before-current-session.sqlite3'
                if not backup.exists():
                    with sqlite3.connect(backup) as saved:target.backup(saved)
                    backup.chmod(0o600)
                target.execute('BEGIN IMMEDIATE')
                counts=sync_terminal_session(source,target,SESSION)
                target.commit()
            for relative in plan['files']:
                if hashlib.sha256((runtime/relative).read_bytes()).hexdigest()==plan['files'][relative]['after']:
                    continue
                backup=STATE/'runtime-before'/relative;backup.parent.mkdir(parents=True,exist_ok=True);backup.write_bytes((runtime/relative).read_bytes());backup.chmod(0o600)
                temporary=(runtime/relative).with_suffix('.owner-tmp');temporary.write_bytes((stage/relative).read_bytes());temporary.replace(runtime/relative)
            dropin=Path.home()/'.config/systemd/user/codex-mobile-bridge-dev.service.d/99-prod-work-owner.conf'
            owner_env=dropin.with_suffix('.env')
            owner_env.write_text('WORK_HUB_URL=http://127.0.0.1:8000\nWORK_HUB_ENVIRONMENT=prod\n')
            dropin.write_text('[Service]\nEnvironmentFile='+str(owner_env)+'\n')
            subprocess.run(['systemctl','--user','daemon-reload'],check=True,timeout=30,capture_output=True)
            save('restarting_idle_dev_forwarder',conversation_copied_to_prod=True,history_rows=counts)
            subprocess.run(['systemctl','--user','restart','codex-mobile-bridge-dev.service'],check=True,timeout=90,capture_output=True)
            for _ in range(45):
                try:
                    d=client.get('/work').raise_for_status().json()
                    if d.get('coordinator',{}).get('environment')=='prod':break
                except httpx.HTTPError:pass
                time.sleep(2)
            else:raise RuntimeError('PROD routing not verified')
            assert httpx.get('http://127.0.0.1:8000/health',timeout=20).raise_for_status().json()['status']=='ok'
            assert httpx.get(f'http://127.0.0.1:8000/sessions/{SESSION}',timeout=20).is_success
            save('verified',owner='prod',publication_environment='dev',dev_forwards_to_prod=True,local_dev_scheduler_disabled=True,conversation_copied_to_prod=True,history_rows=counts,prod_backend_restarted=False)
        finally:
            try:
                client.post('/maintenance/drain',json={'requested':False}).raise_for_status()
            except httpx.HTTPError:
                save('requires_drain_release_verification',owner='prod')

if __name__=='__main__':
    try:main()
    except Exception as exc:
        save('requires_inspection',error_type=type(exc).__name__)
        raise
