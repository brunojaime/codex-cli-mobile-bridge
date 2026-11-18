"""Restore a private SQLite export; reject migrations that rewrite existing facts."""
import hashlib
import json
from pathlib import Path
import sqlite3
import sys


def snapshot(db):
    result = {}
    for (table,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '_cf_%'"):
        quoted = '"' + table.replace('"', '""') + '"'
        columns = [r[1] for r in db.execute('PRAGMA table_info(' + quoted + ')')]
        selection = ','.join('"' + c.replace('"', '""') + '"' for c in columns)
        rows = list(db.execute('SELECT ' + selection + ' FROM ' + quoted))
        encoded = sorted(json.dumps(row, default=lambda value: {'blob': value.hex()}, ensure_ascii=False) for row in rows)
        result[table] = {'columns': columns, 'rows': len(rows), 'digest': hashlib.sha256('\n'.join(encoded).encode()).hexdigest()}
    return result


def drill(backup, migrations):
    with sqlite3.connect(':memory:') as db:
        db.executescript(Path(backup).read_text())
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
        before = snapshot(db)
        for migration in migrations:
            db.executescript(Path(migration).read_text())
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
        for table, expected in before.items():
            quoted = '"' + table.replace('"', '""') + '"'
            columns = {r[1] for r in db.execute('PRAGMA table_info(' + quoted + ')')}
            assert set(expected['columns']) <= columns, 'Historical columns removed'
            selection = ','.join('"' + c.replace('"', '""') + '"' for c in expected['columns'])
            rows = list(db.execute('SELECT ' + selection + ' FROM ' + quoted))
            encoded = sorted(json.dumps(row, default=lambda value: {'blob': value.hex()}, ensure_ascii=False) for row in rows)
            assert len(rows) == expected['rows'] and hashlib.sha256('\n'.join(encoded).encode()).hexdigest() == expected['digest'], 'Historical facts changed'
        after = snapshot(db)
        business = {table: value['rows'] for table, value in after.items() if table != 'd1_migrations' and not table.startswith('platform_') and table != 'sea_access_requests'}
        return {'restored': True, 'integrity': 'ok', 'historical_tables_preserved': len(before), 'migrations_tested': len(migrations), 'expected_business_counts': business}


if __name__ == '__main__':
    print(json.dumps(drill(sys.argv[1], sys.argv[2:])))
