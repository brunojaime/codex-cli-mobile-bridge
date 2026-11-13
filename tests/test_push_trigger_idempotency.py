from pathlib import Path
import sqlite3
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("action", ["insert", "update"])
def test_reconciled_messages_cannot_duplicate_notification_intent(action):
    with sqlite3.connect(":memory:") as db:
        db.execute(
            "CREATE TABLE messages(id TEXT PRIMARY KEY, role TEXT, status TEXT, session_id TEXT, run_id TEXT, job_id TEXT)"
        )
        db.executescript(
            (ROOT / "services/notifications/migrations/001-push.sql").read_text()
        )
        migration = (
            ROOT / "services/notifications/migrations/002-trigger-idempotency.sql"
        )
        if migration.exists():
            db.executescript(migration.read_text())
        db.execute(
            "INSERT INTO messages VALUES ('one','assistant','completed','session','run','job-one')"
        )
        event_id = db.execute("SELECT id FROM bridge_push_events").fetchone()[0]
        if action == "insert":
            db.execute(
                "INSERT OR ABORT INTO messages VALUES ('two','assistant','completed','session','run','job-two')"
            )
        else:
            db.execute(
                "INSERT INTO messages VALUES ('two','assistant','running','session','run','job-two')"
            )
            db.execute("UPDATE OR ABORT messages SET status='completed' WHERE id='two'")
        assert db.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 2
        assert db.execute("SELECT id FROM bridge_push_events").fetchall() == [
            (event_id,)
        ]
