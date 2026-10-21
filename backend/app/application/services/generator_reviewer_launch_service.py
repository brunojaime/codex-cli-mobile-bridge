"""Durable, one-shot handoff to the existing Generator/Reviewer engine."""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
from pathlib import Path
import sqlite3
from uuid import UUID, uuid5, NAMESPACE_URL

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.domain.entities.agent_configuration import (
    AgentConfiguration,
    AgentId,
    AgentPreset,
    AgentTriggerSource,
    TurnBudgetMode,
)
from backend.app.domain.entities.chat_message import ChatMessageAuthorType


class GeneratorReviewerLaunch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_session_id: UUID
    source_message_id: UUID
    title: str = Field(min_length=1, max_length=200)
    generator_prompt: str = Field(min_length=1, max_length=12_000)
    reviewer_prompt: str = Field(min_length=1, max_length=12_000)
    kickoff: str = Field(min_length=1, max_length=10_000)
    generator_turns: int = Field(default=25, ge=1, le=2**63 - 1, strict=True)
    reviewer_turns: int = Field(default=25, ge=1, le=2**63 - 1, strict=True)

    @field_validator("title", "generator_prompt", "reviewer_prompt", "kickoff")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("El texto no puede estar vacío")
        return value


class LaunchConflict(ValueError):
    pass


class GeneratorReviewerLaunchService:
    def __init__(self, message_service, database: str | Path):
        self.messages = message_service
        self.database = Path(database)

    @contextmanager
    def _ledger(self):
        self.database.parent.mkdir(parents=True, exist_ok=True)
        # flock also serializes independent service instances/processes. No LLM
        # runs are awaited under this lock: submit_message only enqueues a job.
        with self.database.with_suffix(".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            db = sqlite3.connect(self.database)
            db.row_factory = sqlite3.Row
            try:
                db.execute("""CREATE TABLE IF NOT EXISTS launches (
                    launch_id TEXT PRIMARY KEY, digest TEXT NOT NULL,
                    source_session_id TEXT NOT NULL, source_message_id TEXT NOT NULL,
                    session_id TEXT NOT NULL, title TEXT NOT NULL,
                    generator_turns INTEGER NOT NULL, reviewer_turns INTEGER NOT NULL,
                    state TEXT NOT NULL, job_id TEXT, problem TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )""")
                db.commit()
                yield db
            finally:
                db.close()
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _result(self, row, *, reused: bool) -> dict:
        result = dict(row)
        result.pop("digest")
        result["reused"] = reused
        result["chat_link"] = f"codex-bridge://chat/{row['session_id']}"
        result["session_available"] = (
            self.messages.get_session(row["session_id"]) is not None
        )
        return result

    def _read(self, db, launch_id):
        return db.execute(
            "SELECT * FROM launches WHERE launch_id=?", (launch_id,)
        ).fetchone()

    def _reconcile(self, db, row):
        if row["state"] in {"starting", "uncertain"}:
            jobs = [
                job
                for job in self.messages.list_stored_jobs_for_session(row["session_id"])
                if job.agent_id == AgentId.GENERATOR
                and job.trigger_source == AgentTriggerSource.USER
            ]
            if len(jobs) == 1:
                db.execute(
                    "UPDATE launches SET state='started', job_id=?, problem=NULL WHERE launch_id=?",
                    (jobs[0].id, row["launch_id"]),
                )
            else:
                # A process may have died after provider submission but before
                # save_turn. Never infer that absence from SQLite means no job.
                db.execute(
                    "UPDATE launches SET state='uncertain', problem=? WHERE launch_id=?",
                    (
                        "Arranque sin confirmación persistida; inspeccionar el chat antes de otro pedido.",
                        row["launch_id"],
                    ),
                )
            db.commit()
        return self._read(db, row["launch_id"])

    def get(self, launch_id: str) -> dict | None:
        with self._ledger() as db:
            row = self._read(db, launch_id)
            return self._result(self._reconcile(db, row), reused=True) if row else None

    def launch(self, request: GeneratorReviewerLaunch) -> dict:
        source_id, message_id = (
            str(request.source_session_id),
            str(request.source_message_id),
        )
        source = self.messages.get_session(source_id)
        if source is None:
            raise ValueError("La conversación de origen no existe en este backend")
        if not any(
            m.id == message_id and m.author_type == ChatMessageAuthorType.HUMAN
            for m in self.messages.list_messages(source_id)
        ):
            raise ValueError(
                "El pedido debe ser un mensaje humano de la conversación de origen"
            )
        launch_id = str(
            uuid5(NAMESPACE_URL, f"generator-reviewer:{source_id}:{message_id}")
        )
        session_id = str(uuid5(NAMESPACE_URL, f"generator-reviewer-target:{launch_id}"))
        digest = hashlib.sha256(
            json.dumps(request.model_dump(mode="json"), sort_keys=True).encode()
        ).hexdigest()
        with self._ledger() as db:
            row = self._read(db, launch_id)
            if row:
                if row["digest"] != digest:
                    raise LaunchConflict(
                        "Este pedido ya tiene otro lanzamiento. Consultá su estado; un cambio requiere un nuevo pedido humano."
                    )
                if row["state"] not in {"reserved", "configured"}:
                    return self._result(self._reconcile(db, row), reused=True)
            else:
                db.execute(
                    """INSERT INTO launches
                    (launch_id,digest,source_session_id,source_message_id,session_id,title,generator_turns,reviewer_turns,state)
                    VALUES (?,?,?,?,?,?,?,?,'reserved')""",
                    (
                        launch_id,
                        digest,
                        source_id,
                        message_id,
                        session_id,
                        request.title,
                        request.generator_turns,
                        request.reviewer_turns,
                    ),
                )
                db.commit()
            try:
                target = self.messages.get_session(session_id)
                if target is None:
                    target = self.messages.create_session(
                        title=request.title,
                        workspace_path=source.workspace_path,
                        session_id=session_id,
                    )
                if self.messages.list_stored_jobs_for_session(session_id):
                    raise LaunchConflict(
                        "El chat reservado ya tiene actividad; no se enviará otro kickoff"
                    )
                config = AgentConfiguration.default().normalized()
                config.preset = AgentPreset.REVIEW
                config.turn_budget_mode = TurnBudgetMode.EACH_AGENT
                for agent in config.agents.values():
                    agent.enabled = agent.agent_id in {
                        AgentId.GENERATOR,
                        AgentId.REVIEWER,
                    }
                for agent_id, prompt, turns in (
                    (
                        AgentId.GENERATOR,
                        request.generator_prompt,
                        request.generator_turns,
                    ),
                    (AgentId.REVIEWER, request.reviewer_prompt, request.reviewer_turns),
                ):
                    config.agents[agent_id].prompt = prompt
                    config.agents[agent_id].max_turns = turns
                self.messages.update_agent_configuration(
                    session_id=session_id, configuration=config
                )
                db.execute(
                    "UPDATE launches SET state='configured' WHERE launch_id=?",
                    (launch_id,),
                )
                db.commit()
            except Exception:
                db.execute(
                    "UPDATE launches SET state='failed', problem=? WHERE launch_id=?",
                    (
                        "No se pudo configurar el chat. No se envió el kickoff.",
                        launch_id,
                    ),
                )
                db.commit()
                return self._result(self._read(db, launch_id), reused=bool(row))
            db.execute(
                "UPDATE launches SET state='starting' WHERE launch_id=?", (launch_id,)
            )
            db.commit()
            try:
                job = self.messages.submit_message(
                    request.kickoff, session_id=session_id
                )
            except Exception:
                # An exception is not proof that the provider never started.
                return self._result(
                    self._reconcile(db, self._read(db, launch_id)), reused=bool(row)
                )
            db.execute(
                "UPDATE launches SET state='started', job_id=? WHERE launch_id=?",
                (job.id, launch_id),
            )
            db.commit()
            return self._result(self._read(db, launch_id), reused=bool(row))
