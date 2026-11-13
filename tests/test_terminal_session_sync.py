import sqlite3
import pytest
from scripts.sync_terminal_session import sync_terminal_session
from scripts.migrate_work_to_prod import MigrationConflict


def store():
    db=sqlite3.connect(':memory:')
    db.executescript('''CREATE TABLE sessions(id TEXT PRIMARY KEY,workspace_path TEXT,active_agent_run_id TEXT,title TEXT);
    CREATE TABLE messages(id TEXT PRIMARY KEY,session_id TEXT,content TEXT);
    CREATE TABLE jobs(id TEXT PRIMARY KEY,session_id TEXT,status TEXT,auto_chain_processed INTEGER);
    CREATE TABLE agent_runs(id TEXT PRIMARY KEY,session_id TEXT);
    CREATE TABLE turn_summaries(id TEXT PRIMARY KEY,session_id TEXT);''')
    return db


def test_incremental_sync_keeps_original_ids_and_does_not_replay_jobs():
    source,target=store(),store()
    for db in (source,target):
        db.execute("INSERT INTO sessions VALUES ('chat','/project',NULL,'old')")
        db.execute("INSERT INTO messages VALUES ('old','chat','previous')")
        db.execute("INSERT INTO jobs VALUES ('job','chat','completed',1)")
    source.execute("UPDATE jobs SET auto_chain_processed=0")
    source.execute("UPDATE sessions SET title='latest'")
    source.execute("INSERT INTO messages VALUES ('new','chat','latest response')")
    counts=sync_terminal_session(source,target,'chat')
    assert counts['messages']==1
    assert target.execute('SELECT COUNT(*) FROM messages').fetchone()[0]==2
    assert target.execute('SELECT title FROM sessions').fetchone()[0]=='latest'
    assert target.execute('SELECT auto_chain_processed FROM jobs').fetchone()[0]==1
    assert sync_terminal_session(source,target,'chat')['messages']==0


def test_independent_prod_activity_is_preserved_by_rejecting_merge():
    source,target=store(),store()
    for db in (source,target):db.execute("INSERT INTO sessions VALUES ('chat','/project',NULL,'old')")
    target.execute("INSERT INTO messages VALUES ('prod-only','chat','do not overwrite')")
    with pytest.raises(MigrationConflict,match='independent'):sync_terminal_session(source,target,'chat')
    assert target.execute('SELECT content FROM messages').fetchone()[0]=='do not overwrite'


def test_active_conversation_cannot_be_copied():
    source,target=store(),store()
    source.execute("INSERT INTO sessions VALUES ('chat','/project','active','old')")
    with pytest.raises(MigrationConflict,match='active'):sync_terminal_session(source,target,'chat')
