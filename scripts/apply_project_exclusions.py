"""Apply the owner's exact workspace exclusions without touching project files."""
from contextlib import ExitStack
from pathlib import Path
import fcntl,json,sqlite3
from datetime import datetime,timezone

ROOT=Path('/home/batata/Projects/codex-cli-mobile-bridge')
registry=json.loads(Path('/home/batata/Projects/.bridge-automation-exclusions.json').read_text())
paths=set(registry['paths'])
results=[]
with ExitStack() as stack:
    databases=[ROOT/'.data/chat_store.work.sqlite3',ROOT/'.run/dev-backend-8118/data/chat_store.work.sqlite3']
    for lock in sorted(p.with_suffix(ext) for p in databases for ext in ('.worker.lock','.lock')):
        f=stack.enter_context(lock.open('a'));fcntl.flock(f,fcntl.LOCK_EX)
    for path in databases:
        db=stack.enter_context(sqlite3.connect(path,timeout=30));db.execute('BEGIN IMMEDIATE')
        cancelled=0
        for workspace in paths:
            active=db.execute("SELECT id FROM work_tasks WHERE workspace=? AND status IN ('starting','running','delivering','uncertain')",(workspace,)).fetchall()
            assert not active,'Excluded project has active work; do not interrupt'
            db.execute('DELETE FROM work_policies WHERE workspace=?',(workspace,))
            db.execute('INSERT INTO work_project_settings VALUES (?,?) ON CONFLICT(workspace) DO UPDATE SET payload=excluded.payload',(workspace,json.dumps({'automatic_execution':False})))
            cancelled+=db.execute("UPDATE work_tasks SET status='cancelled',problem='Excluido por instrucción del titular 09/11/2026' WHERE workspace=? AND status IN ('queued','blocked')",(workspace,)).rowcount
        db.execute('CREATE TABLE IF NOT EXISTS automation_exclusions(workspace TEXT PRIMARY KEY)')
        db.executemany('INSERT OR IGNORE INTO automation_exclusions VALUES (?)',[(p,) for p in paths])
        # Durable admission guard; no excluded workspace can acquire an actionable task.
        for operation in ('INSERT','UPDATE'):
            name='owner_project_exclusion_'+operation.lower()
            db.execute(f'''CREATE TRIGGER IF NOT EXISTS {name} BEFORE {operation} ON work_tasks
              WHEN NEW.workspace IN (SELECT workspace FROM automation_exclusions)
              AND NEW.status IN ('queued','blocked','starting','running','delivering','uncertain')
              BEGIN SELECT RAISE(ABORT,'Project excluded from automation by owner'); END''')
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        db.commit();results.append({'database':str(path.relative_to(ROOT)),'excluded':len(paths),'cancelled_pending':cancelled})
config=ROOT/'.data/nightly-discovery/config.json';data=json.loads(config.read_text());data['projects']=[p for p in data['projects'] if p['workspace_path'] not in paths];config.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
registry.update(applied_at=datetime.now(timezone.utc).isoformat(),results=results)
(ROOT/'reports/project-automation/exclusiones-20261109.json').write_text(json.dumps(registry,ensure_ascii=False,indent=2)+'\n')
with Path('/home/batata/Projects/AGENTS.md').open('a') as f:f.write('\n## Exclusión completa de proyectos sin clasificar — 09/11/2026\n\nEl titular excluyó de búsqueda nocturna, backlog, implementación y publicación automática todos los workspaces sin clasificar del inventario `codex-cli-mobile-bridge/reports/project-automation/inventario-20261109.json`, además de Pehuen y Simposio. Registro exacto: `/home/batata/Projects/.bridge-automation-exclusions.json`. No borrar ni modificar esas carpetas, ni reactivarlas sin instrucción posterior explícita. La exclusión de una biblioteca como proyecto independiente no impide que los proyectos activos consuman sus integraciones/versiones compartidas. Los diez proyectos activos previamente acordados conservan su alcance; nienfo.com permanece como documentación agrupada de nienfos.com.\n')
print(json.dumps(results))
