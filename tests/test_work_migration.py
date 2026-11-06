import sqlite3
import pytest
from scripts.migrate_work_to_prod import merge_rows, MigrationConflict, archive_source


def test_merge_preserves_ids_payload_and_paused_choice_with_different_column_order():
    source=sqlite3.connect(':memory:');target=sqlite3.connect(':memory:')
    source.execute('CREATE TABLE tasks(id TEXT PRIMARY KEY,payload TEXT,status TEXT)')
    target.execute('CREATE TABLE tasks(status TEXT,id TEXT PRIMARY KEY,payload TEXT)')
    source.execute('INSERT INTO tasks VALUES (?,?,?)',('same-id','{"attachments":["original.png"]}','blocked'))
    with target:
        assert merge_rows(source,target,'tasks') == 1
    assert target.execute('SELECT id,payload,status FROM tasks').fetchall() == source.execute('SELECT * FROM tasks').fetchall()
    assert merge_rows(source,target,'tasks') == 0
    target.execute("UPDATE tasks SET status='running'")
    with pytest.raises(MigrationConflict):merge_rows(source,target,'tasks')


def test_schema_mismatch_is_rejected_before_copy():
    source=sqlite3.connect(':memory:');target=sqlite3.connect(':memory:')
    source.execute('CREATE TABLE tasks(id TEXT PRIMARY KEY,payload TEXT)')
    target.execute('CREATE TABLE tasks(id TEXT PRIMARY KEY)')
    with pytest.raises(MigrationConflict):merge_rows(source,target,'tasks')
    assert target.execute('SELECT COUNT(*) FROM tasks').fetchone()[0] == 0


def test_development_copy_is_archived_without_deleting_history():
    source=sqlite3.connect(':memory:')
    source.executescript('''
    CREATE TABLE work_tasks(id TEXT PRIMARY KEY,workspace TEXT,status TEXT,problem TEXT);
    CREATE TABLE work_policies(workspace TEXT PRIMARY KEY,payload TEXT);
    CREATE TABLE work_project_settings(workspace TEXT PRIMARY KEY,payload TEXT);
    CREATE TABLE work_meta(name TEXT PRIMARY KEY,value TEXT);
    INSERT INTO work_tasks VALUES ('pending','/rd','blocked',NULL);
    INSERT INTO work_tasks VALUES ('past','/rd','completed',NULL);
    INSERT INTO work_policies VALUES ('/rd','{"enabled":true,"autonomous":true}');
    INSERT INTO work_project_settings VALUES ('/rd','{"automatic_execution":false}');
    ''')
    archive_source(source)
    assert source.execute("SELECT status FROM work_tasks WHERE id='pending'").fetchone()[0]=='cancelled'
    assert source.execute("SELECT status FROM work_tasks WHERE id='past'").fetchone()[0]=='completed'
    import json
    assert json.loads(source.execute('SELECT payload FROM work_policies').fetchone()[0])=={'enabled':False,'autonomous':False}
    assert json.loads(source.execute('SELECT payload FROM work_project_settings').fetchone()[0])['automatic_execution'] is False
