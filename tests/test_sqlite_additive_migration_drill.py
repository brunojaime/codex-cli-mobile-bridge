import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('migration_drill', Path(__file__).parents[1] / 'scripts/project_work/sqlite_additive_migration_drill.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_additive_schema_restores_without_rewriting_existing_values(tmp_path):
    backup = tmp_path / 'private.sql'
    backup.write_text("CREATE TABLE facts(id TEXT PRIMARY KEY, amount INTEGER, evidence BLOB); INSERT INTO facts VALUES('a',123,X'0011');")
    migration = tmp_path / 'add.sql'
    migration.write_text('ALTER TABLE facts ADD COLUMN note TEXT; CREATE TABLE detail(id TEXT PRIMARY KEY);')
    assert module.drill(backup, [migration])['historical_tables_preserved'] == 1


@pytest.mark.parametrize('sql', ["UPDATE facts SET amount=124", 'DELETE FROM facts', 'DROP TABLE facts', "INSERT INTO facts VALUES('b',456)"])
def test_historical_changes_block_before_any_remote_operation(tmp_path, sql):
    backup = tmp_path / 'private.sql'
    backup.write_text("CREATE TABLE facts(id TEXT PRIMARY KEY, amount INTEGER); INSERT INTO facts VALUES('a',123);")
    migration = tmp_path / 'unsafe.sql'
    migration.write_text(sql)
    with pytest.raises((AssertionError, module.sqlite3.Error)):
        module.drill(backup, [migration])
