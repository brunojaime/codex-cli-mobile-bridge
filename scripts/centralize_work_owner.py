"""Move remaining DEV project work to PROD under both scheduler/admission locks.
No jobs are launched and no backend is restarted. Backups are private.
"""
import fcntl
import json
import os
from pathlib import Path
import sqlite3
from contextlib import ExitStack
from datetime import datetime, timezone
from scripts.migrate_work_to_prod import merge_rows, copy_history, archive_source

ROOT = Path('/home/batata/Projects/codex-cli-mobile-bridge')
SOURCE = ROOT / '.run/dev-backend-8118/data/chat_store.work.sqlite3'
TARGET = ROOT / '.data/chat_store.work.sqlite3'
WORKSPACES = [str(ROOT), '/home/batata/Projects/sea']
PRIVATE = ROOT / '.run/centralize-prod-20261109'
REPORT = ROOT / 'reports/project-automation/coordinator-owner-20261109'


def execute():
    PRIVATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    PRIVATE.chmod(0o700)
    REPORT.mkdir(parents=True, exist_ok=True)
    with ExitStack() as stack:
        for path in sorted([p.with_suffix(ext) for p in (SOURCE,TARGET) for ext in ('.worker.lock','.lock')]):
            handle=stack.enter_context(path.open('a'))
            fcntl.flock(handle,fcntl.LOCK_EX)
        source=stack.enter_context(sqlite3.connect(SOURCE,timeout=30))
        target=stack.enter_context(sqlite3.connect(TARGET,timeout=30))
        old=stack.enter_context(sqlite3.connect(SOURCE.with_name('chat_store.sqlite3'),timeout=30))
        new=stack.enter_context(sqlite3.connect(TARGET.with_name('chat_store.sqlite3'),timeout=30))
        for label,db in [('dev-work',source),('prod-work',target),('prod-chat',new)]:
            path=PRIVATE/(label+'.sqlite3')
            if not path.exists():
                with sqlite3.connect(path) as saved:db.backup(saved)
                path.chmod(0o600)
        assert not source.execute("SELECT 1 FROM work_tasks WHERE status IN ('starting','running','delivering','uncertain')").fetchone(), 'DEV has active work'
        assert not source.execute("SELECT 1 FROM work_observations WHERE status IN ('starting','running')").fetchone(), 'DEV has active observer'
        target.execute('BEGIN IMMEDIATE');new.execute('BEGIN IMMEDIATE')
        filtered=sqlite3.connect(':memory:')
        source.backup(filtered)
        marks=','.join('?' for _ in WORKSPACES)
        filtered.execute('DELETE FROM work_tasks WHERE workspace NOT IN ('+marks+')',WORKSPACES)
        filtered.execute('DELETE FROM work_observations WHERE workspace NOT IN ('+marks+')',WORKSPACES)
        copied=[]
        for ident,workspace in filtered.execute('SELECT id,workspace FROM work_tasks').fetchall():
            previous=target.execute('SELECT payload,digest,status FROM work_tasks WHERE id=?',(ident,)).fetchone()
            if previous:
                incoming=source.execute('SELECT payload,digest,status FROM work_tasks WHERE id=?',(ident,)).fetchone()
                assert incoming == previous, 'Existing PROD task differs; reconcile manually'
                filtered.execute('DELETE FROM work_tasks WHERE id=?',(ident,))
                continue
            merge_rows(source,target,'work_tasks','id=?',(ident,));copied.append(ident)
            for values in source.execute('SELECT task_id,kind,text,created_at FROM work_events WHERE task_id=? ORDER BY seq',(ident,)):
                if not target.execute('SELECT 1 FROM work_events WHERE task_id=? AND kind=? AND text=? AND created_at=?',values).fetchone():
                    target.execute('INSERT INTO work_events(task_id,kind,text,created_at) VALUES (?,?,?,?)',values)
        for workspace in WORKSPACES:
            merge_rows(source,target,'work_observations','workspace=?',(workspace,))
            merge_rows(source,target,'work_questions','workspace=?',(workspace,))
        history=copy_history(filtered,old,new)
        workspace=str(ROOT)
        policy=json.loads(source.execute('SELECT payload FROM work_policies WHERE workspace=?',(workspace,)).fetchone()[0])
        policy['execution_context']='El coordinador y sus chats se ejecutan exclusivamente en Bridge PROD. DEV indica sólo el destino publicado de la app. '+policy['execution_context']
        target.execute('INSERT INTO work_policies VALUES (?,?) ON CONFLICT(workspace) DO UPDATE SET payload=excluded.payload',(workspace,json.dumps(policy)))
        target.execute('INSERT INTO work_project_settings VALUES (?,?) ON CONFLICT(workspace) DO UPDATE SET payload=excluded.payload',(workspace,json.dumps({'automatic_execution':True})))
        assert not new.execute('PRAGMA foreign_key_check').fetchone()
        assert target.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        new.commit();target.commit()  # Commit preserved history before retiring source admission.
        archive_source(source);source.commit()
        config_path=ROOT/'.data/nightly-discovery/config.json'
        config=json.loads(config_path.read_text())
        config['bridge_url']='http://127.0.0.1:8000'
        for project in config['projects']:
            project.pop('execution_bridge_url',None)
            if project['name']=='codex-cli-mobile-bridge':
                project['focus']=project.get('focus','').replace('La ejecución y publicación pertenecen a DEV.','La ejecución, los chats y el coordinador pertenecen a Bridge PROD; sólo el destino de publicación de la aplicación es DEV.')
        temporary=config_path.with_suffix('.owner-tmp');temporary.write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n');temporary.replace(config_path)
        (ROOT/'.data/project_work/bridge/policy.json').write_text(json.dumps(policy,ensure_ascii=False,indent=2)+'\n')
        result={'checked_at':datetime.now(timezone.utc).isoformat(),'owner':'prod','publication_environment':'dev','copied_task_ids':copied,'history_rows_copied':history,'task_ids_preserved':True,'dev_policies_disabled':True,'nightly_exceptions':0,'no_jobs_launched':True,'backend_restarted':False}
        (REPORT/'status.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result))

if __name__=='__main__':execute()
