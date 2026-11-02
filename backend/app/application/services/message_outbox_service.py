"""Durable intake receipts. Transcription never holds the HTTP request open.

One pending intake per conversation is processed at a time. Failed/uncertain
intakes deliberately hold later turns until explicitly retried or discarded.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import fcntl
import json
from pathlib import Path
import sqlite3
import threading
from typing import Any

from backend.app.domain.entities.codex_options import CodexRunOptions


class OutboxConflict(ValueError):
    pass


class MessageOutboxService:
    def __init__(
        self,
        *,
        database_path: str,
        message_service,
        transcriber,
        validate_submission=None,
        max_workers: int = 2,
    ):
        self._service = message_service
        self._transcriber = transcriber
        self._validate = validate_submission or (lambda payload: None)
        self._lock = threading.RLock()
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="message-outbox"
        )
        self._limit = max_workers
        self._active = 0
        self._closed = False
        self._process_lock = None
        if database_path != ":memory:":
            Path(database_path).parent.mkdir(parents=True, exist_ok=True)
            self._process_lock = open(database_path + ".lock", "a")
            try:
                fcntl.flock(self._process_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                self._process_lock.close()
                raise RuntimeError(
                    "La cola de mensajes requiere un único proceso por base de datos."
                )
        self._db = sqlite3.connect(database_path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.execute("""CREATE TABLE IF NOT EXISTS message_intake (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            id TEXT NOT NULL UNIQUE, lane TEXT NOT NULL, fingerprint TEXT NOT NULL,
            payload TEXT NOT NULL, audio BLOB, state TEXT NOT NULL,
            transcript TEXT, result TEXT, error TEXT)""")
        # Transcription is safe to repeat. Submission may already have reached the
        # provider: reconcile its saved turn instead of blindly executing again.
        self._db.execute(
            "UPDATE message_intake SET state='queued' WHERE state='transcribing'"
        )
        for row in self._db.execute(
            "SELECT * FROM message_intake WHERE state='submitting'"
        ).fetchall():
            job = self._recover_submission(row["id"])
            if job:
                self._complete(row["id"], job)
            else:
                self._db.execute(
                    "UPDATE message_intake SET state='uncertain', error=? WHERE id=?",
                    (
                        "El servidor se reinició durante la entrega. Revisá el chat antes de descartar este envío; no se repetirá automáticamente.",
                        row["id"],
                    ),
                )
        self._db.commit()

    def accept(
        self, submission_id: str, payload: dict[str, Any], audio: bytes | None
    ) -> dict:
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        fingerprint = hashlib.sha256(
            canonical.encode() + b"\0" + (audio or b"")
        ).hexdigest()
        # Unknown sessions use an explicit client conversation key. The client
        # resolves the assigned session before sending subsequent turns.
        lane = payload.get("session_id") or payload["conversation_key"]
        with self._lock:
            row = self._db.execute(
                "SELECT id,fingerprint,state,result,error FROM message_intake WHERE id=?",
                (submission_id,),
            ).fetchone()
            if row:
                if row["fingerprint"] != fingerprint:
                    raise OutboxConflict(
                        "El ID de envío ya corresponde a otro contenido."
                    )
                return self._receipt(row)
            if (
                self._db.execute(
                    "SELECT count(*) FROM message_intake WHERE state NOT IN ('accepted','discarded')"
                ).fetchone()[0]
                >= 1000
            ):
                raise OutboxConflict(
                    "La cola del servidor está llena. Reintentá más tarde."
                )
            existing_job = self._service.find_client_submission(submission_id)
            self._db.execute(
                "INSERT INTO message_intake (id,lane,fingerprint,payload,audio,state) VALUES (?,?,?,?,?,'queued')",
                (submission_id, lane, fingerprint, canonical, audio),
            )
            if existing_job:
                self._complete(submission_id, existing_job)
            self._db.commit()
            result = self.get(submission_id)
        self.wake()
        return result

    def get(self, submission_id: str) -> dict:
        with self._lock:
            row = self._db.execute(
                "SELECT id,state,result,error FROM message_intake WHERE id=?",
                (submission_id,),
            ).fetchone()
            if row is None:
                raise KeyError(submission_id)
            return self._receipt(row)

    def retry(self, submission_id: str) -> dict:
        with self._lock:
            receipt = self.get(submission_id)
            if receipt["state"] == "uncertain":
                raise OutboxConflict(
                    "Entrega incierta: revisá el chat antes de descartar; no es seguro repetirla."
                )
            if receipt["state"] == "failed":
                self._db.execute(
                    "UPDATE message_intake SET state='queued', error=NULL WHERE id=?",
                    (submission_id,),
                )
                self._db.commit()
        self.wake()
        return self.get(submission_id)

    def discard(self, submission_id: str) -> dict:
        with self._lock:
            state = self.get(submission_id)["state"]
            if state not in ("failed", "uncertain", "queued", "discarded"):
                raise OutboxConflict("Este envío ya está procesándose o fue aceptado.")
            self._db.execute(
                "UPDATE message_intake SET state='discarded', audio=NULL WHERE id=?",
                (submission_id,),
            )
            self._db.commit()
        self.wake()
        return self.get(submission_id)

    @staticmethod
    def _receipt(row) -> dict:
        return {
            "id": row["id"],
            "state": row["state"],
            "error": row["error"],
            "job": json.loads(row["result"]) if row["result"] else None,
        }

    def wake(self):
        with self._lock:
            if self._closed:
                return
            while self._active < self._limit:
                row = self._db.execute("""SELECT a.* FROM message_intake a
                    WHERE a.state='queued' AND NOT EXISTS (
                      SELECT 1 FROM message_intake b WHERE b.lane=a.lane
                      AND b.sequence<a.sequence AND b.state NOT IN ('accepted','discarded'))
                    ORDER BY a.sequence LIMIT 1""").fetchone()
                if not row:
                    return
                self._db.execute(
                    "UPDATE message_intake SET state='transcribing' WHERE id=?",
                    (row["id"],),
                )
                self._db.commit()
                self._active += 1
                self._pool.submit(self._process, dict(row))

    def _process(self, row):
        submission_id = row["id"]
        submitting = False
        try:
            payload = json.loads(row["payload"])
            self._validate(payload)
            text = payload.get("message", "")
            execution = None
            if payload["kind"] == "audio":
                # The original upload is already durable in SQLite. Only a
                # transcriber-compatible temporary copy is needed here.
                import tempfile

                with tempfile.TemporaryDirectory(prefix="bridge-intake-") as directory:
                    path = Path(directory) / "audio"
                    path.write_bytes(row["audio"])
                    transcript = self._transcriber.transcribe(
                        path,
                        filename=payload["filename"],
                        content_type=payload.get("content_type"),
                        language=payload.get("language"),
                    ).strip()
                if not transcript:
                    raise ValueError("La transcripción del audio está vacía.")
                text = self._service._build_audio_display_message(
                    message=text, transcript=transcript
                )
                execution = self._service._build_audio_execution_message(
                    message=payload.get("message"), transcript=transcript
                )
            options = payload.get("codex_options")
            with self._lock:
                self._db.execute(
                    "UPDATE message_intake SET state='submitting' WHERE id=?",
                    (submission_id,),
                )
                self._db.commit()
            submitting = True
            job = self._service.submit_message(
                text,
                session_id=payload.get("session_id"),
                workspace_path=payload.get("workspace_path"),
                execution_message=execution,
                codex_options=CodexRunOptions(**options).normalized()
                if options
                else None,
                client_submission_id=submission_id,
            )
            with self._lock:
                self._complete(submission_id, job)
                self._db.commit()
        except Exception as exc:
            # Before submission, retrying is safe. After it began, reconcile or
            # stop rather than risk duplicate execution after an ambiguous error.
            with self._lock:
                job = self._recover_submission(submission_id) if submitting else None
                if job:
                    self._complete(submission_id, job)
                else:
                    self._db.execute(
                        "UPDATE message_intake SET state=?, error=? WHERE id=?",
                        (
                            "uncertain" if submitting else "failed",
                            str(exc),
                            submission_id,
                        ),
                    )
                self._db.commit()
        finally:
            with self._lock:
                self._active -= 1
            self.wake()

    def _recover_submission(self, submission_id):
        try:
            return self._service.find_client_submission(submission_id)
        except Exception:
            # A broken repository cannot establish whether execution began.
            return None

    def _complete(self, submission_id, job):
        result = {
            "job_id": job.id,
            "session_id": job.session_id,
            "status": job.status.value,
            "agent_id": job.agent_id.value,
            "agent_type": job.agent_type.value,
            "run_id": job.run_id,
            "provider_session_id": job.provider_session_id,
            "user_text": job.message,
        }
        self._db.execute(
            "UPDATE message_intake SET state='accepted',result=?,error=NULL,audio=NULL WHERE id=?",
            (json.dumps(result), submission_id),
        )

    def close(self):
        with self._lock:
            self._closed = True
        self._pool.shutdown(wait=True)
        self._db.close()
        if self._process_lock:
            self._process_lock.close()
