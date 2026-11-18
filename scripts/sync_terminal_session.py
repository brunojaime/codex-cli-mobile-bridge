"""Incrementally preserve a moved conversation without replay or losing PROD activity."""
import sqlite3
from scripts.migrate_work_to_prod import MigrationConflict, merge_rows


def sync_terminal_session(source, target, session):
    for db in (source,target):
        row=db.execute('SELECT active_agent_run_id FROM sessions WHERE id=?',(session,)).fetchone()
        if row and row[0]:raise MigrationConflict('Conversation still active')
        if db.execute("SELECT 1 FROM jobs WHERE session_id=? AND status NOT IN ('completed','failed','cancelled')",(session,)).fetchone():
            raise MigrationConflict('Conversation still has accepted work')
    source_ids={r[0] for r in source.execute('SELECT id FROM messages WHERE session_id=?',(session,))}
    target_ids={r[0] for r in target.execute('SELECT id FROM messages WHERE session_id=?',(session,))}
    if not target_ids.issubset(source_ids):raise MigrationConflict('PROD has independent conversation activity')
    old=target.execute('SELECT workspace_path FROM sessions WHERE id=?',(session,)).fetchone()
    current=source.execute('SELECT workspace_path FROM sessions WHERE id=?',(session,)).fetchone()
    if not current or old and old!=current:raise MigrationConflict('Conversation workspace differs')
    counts={}
    # Refresh only session metadata; existing message/job contents remain immutable.
    if old:
        columns=[r[1] for r in source.execute('PRAGMA table_info(sessions)')]
        assert set(columns)=={r[1] for r in target.execute('PRAGMA table_info(sessions)')}
        row=source.execute('SELECT '+','.join('"'+c+'"' for c in columns)+' FROM sessions WHERE id=?',(session,)).fetchone()
        target.execute('UPDATE sessions SET '+','.join('"'+c+'"=?' for c in columns)+' WHERE id=?',(*row,session))
    for table in ('sessions','messages','jobs','agent_runs','turn_summaries'):
        where='id=?' if table=='sessions' else 'session_id=?'
        if table=='jobs':
            # Imported terminal jobs must never be automatically chained again.
            columns=[r[1] for r in source.execute('PRAGMA table_info(jobs)')]
            normalized=sqlite3.connect(':memory:')
            normalized.execute(source.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='jobs'").fetchone()[0])
            rows=source.execute('SELECT '+','.join('"'+c+'"' for c in columns)+' FROM jobs WHERE '+where,(session,)).fetchall()
            i=columns.index('auto_chain_processed')
            for row in rows:
                values=list(row);values[i]=1
                normalized.execute('INSERT INTO jobs VALUES ('+','.join('?' for _ in columns)+')',values)
            target.execute('UPDATE jobs SET auto_chain_processed=1 WHERE session_id=?',(session,))
            counts[table]=merge_rows(normalized,target,table,where,(session,));normalized.close()
        else:counts[table]=merge_rows(source,target,table,where,(session,))
    if target.execute('PRAGMA foreign_key_check').fetchone():raise MigrationConflict('Chat foreign key failure')
    return counts
