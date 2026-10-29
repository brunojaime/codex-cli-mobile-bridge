"""Durable admission of feedback batches before any job/session side effect.

An interrupted submission remains uncertain: a timeout never licenses another job.
Only hashes and receipts are stored here, never screenshots, audio or prompts.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
from uuid import uuid4


class SubmissionConflict(ValueError):
    pass


class FeedbackSubmissions:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation prevents a brief world-readable database on first use.
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        except FileExistsError:
            pass
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS submissions (
                id TEXT PRIMARY KEY, digest TEXT NOT NULL, owner TEXT NOT NULL,
                state TEXT NOT NULL, receipt TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""")

    def _connect(self):
        return sqlite3.connect(self.path, timeout=15)

    @staticmethod
    def identity(payload: dict) -> tuple[str, str]:
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        return payload.get("batch_id") or f"feedback-{digest}", digest

    def reserve(self, payload: dict) -> dict:
        identity, digest = self.identity(payload)
        owner = uuid4().hex
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT digest, state, receipt FROM submissions WHERE id=?", (identity,)
            ).fetchone()
            if row:
                if row[0] != digest:
                    raise SubmissionConflict("batch_id_content_conflict")
                return {
                    "id": identity,
                    "state": row[1],
                    "receipt": json.loads(row[2]) if row[2] else None,
                }
            db.execute(
                "INSERT INTO submissions(id,digest,owner,state) VALUES(?,?,?,'reserved')",
                (identity, digest, owner),
            )
        return {"id": identity, "state": "new", "owner": owner}

    def finish(self, identity: str, owner: str, receipt: dict | None):
        with self._connect() as db:
            result = db.execute(
                "UPDATE submissions SET state=?,receipt=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND owner=? AND state='reserved'",
                (
                    "accepted" if receipt else "uncertain",
                    json.dumps(receipt) if receipt else None,
                    identity,
                    owner,
                ),
            )
            if result.rowcount != 1:
                raise SubmissionConflict("submission_ownership_conflict")

    def status(self, identity: str) -> dict | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT state,receipt FROM submissions WHERE id=?", (identity,)
            ).fetchone()
        return (
            {
                "id": identity,
                "state": row[0],
                "receipt": json.loads(row[1]) if row[1] else None,
            }
            if row
            else None
        )
