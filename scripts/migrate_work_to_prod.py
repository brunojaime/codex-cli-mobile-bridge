"""Preserve a paused work queue and its terminal chat history when moving owners.

The caller freezes both schedulers and API admission before calling these helpers.
No models, jobs, Git commands or deployment commands are started by data migration.
"""
from __future__ import annotations
import json
import sqlite3
from uuid import NAMESPACE_URL, uuid5


class MigrationConflict(RuntimeError):
    pass


def merge_rows(source, target, table, where='1', parameters=()):
    """Merge by primary key with explicit column names, rejecting divergent rows."""
    columns = [r[1] for r in source.execute(f'PRAGMA table_info("{table}")')]
    target_columns = [r[1] for r in target.execute(f'PRAGMA table_info("{table}")')]
    if not columns or set(columns) != set(target_columns):
        raise MigrationConflict(f'Incompatible schema: {table}')
    keys = [r[1] for r in target.execute(f'PRAGMA table_info("{table}")') if r[5]]
    if not keys:
        raise MigrationConflict(f'Missing primary key: {table}')
    quoted = ','.join(f'"{c}"' for c in columns)
    count = 0
    for row in source.execute(f'SELECT {quoted} FROM "{table}" WHERE {where}', parameters):
        values = dict(zip(columns, row))
        old = target.execute(f'SELECT {quoted} FROM "{table}" WHERE '+ ' AND '.join(f'"{k}"=?' for k in keys), [values[k] for k in keys]).fetchone()
        if old is not None:
            if tuple(old) != tuple(row):
                if table == 'work_meta' and values['name'] == 'heartbeat':
                    continue
                raise MigrationConflict(f'Existing record differs: {table}')
            continue
        target.execute(f'INSERT INTO "{table}" ({quoted}) VALUES ({",".join("?" for _ in columns)})', row)
        count += 1
    return count


def history_sessions(work):
    result = set()
    for task_id, revision, session_id in work.execute('SELECT id,revision,session_id FROM work_tasks'):
        if session_id:
            result.add(session_id)
            for number in range(1, revision + 1):
                result.add(str(uuid5(NAMESPACE_URL, f'work-task:{task_id}:{number}')))
    result.update(r[0] for r in work.execute('SELECT session_id FROM work_observations') if r[0])
    return result


def copy_history(work, source_chat, target_chat):
    counts = {}
    for session in sorted(history_sessions(work)):
        row = source_chat.execute('SELECT active_agent_run_id FROM sessions WHERE id=?', (session,)).fetchone()
        if row is None:
            continue  # Older revisions can have no accepted execution.
        if row[0] or source_chat.execute("SELECT 1 FROM jobs WHERE session_id=? AND status NOT IN ('completed','failed','cancelled')", (session,)).fetchone():
            raise MigrationConflict('A referenced session is still running')
        for table in ['sessions', 'messages', 'jobs', 'agent_runs', 'turn_summaries']:
            where = 'id=?' if table == 'sessions' else 'session_id=?'
            count = merge_rows(source_chat, target_chat, table, where, (session,))
            counts[table] = counts.get(table, 0) + count
        # Terminal imported history must never trigger an automatic replay.
        target_chat.execute('UPDATE jobs SET auto_chain_processed=1 WHERE session_id=?', (session,))
    return counts


def copy_queue(source, target):
    if source.execute("SELECT 1 FROM work_tasks WHERE status IN ('starting','running','delivering','uncertain')").fetchone():
        raise MigrationConflict('The queue still has an active task')
    if source.execute("SELECT 1 FROM work_observations WHERE status IN ('starting','running')").fetchone():
        raise MigrationConflict('The queue still has an active observer')
    return {table: merge_rows(source, target, table) for table in [
        'work_tasks','work_policies','work_events','work_observations',
        'work_questions','work_project_settings','work_meta',
    ]}


def archive_source(source):
    """DEV retains historical records; only PROD retains actionable pending work."""
    source.execute("UPDATE work_tasks SET status='cancelled',problem='Trasladado a Bridge PROD; continuar allí' WHERE status IN ('queued','blocked')")
    for workspace, payload in source.execute('SELECT workspace,payload FROM work_policies').fetchall():
        policy = json.loads(payload)
        policy.update(enabled=False, autonomous=False)
        source.execute('UPDATE work_policies SET payload=? WHERE workspace=?', (json.dumps(policy), workspace))
    workspaces = {r[0] for r in source.execute('SELECT workspace FROM work_tasks UNION SELECT workspace FROM work_policies UNION SELECT workspace FROM work_project_settings')}
    for workspace in workspaces:
        row = source.execute('SELECT payload FROM work_project_settings WHERE workspace=?', (workspace,)).fetchone()
        value = json.loads(row[0]) if row else {}
        value['automatic_execution'] = False
        source.execute('INSERT INTO work_project_settings VALUES (?,?) ON CONFLICT(workspace) DO UPDATE SET payload=excluded.payload', (workspace,json.dumps(value)))
    source.execute("INSERT INTO work_meta VALUES ('migrated_owner','prod') ON CONFLICT(name) DO UPDATE SET value='prod'")
