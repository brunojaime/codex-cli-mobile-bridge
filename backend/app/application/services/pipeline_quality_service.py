"""Durable work/evidence ledger and bounded runner for the existing DEV pipeline.

Only the runner writes receipts. A model answer, HTTP body, or final summary cannot
create a passing receipt. This is provenance within the trusted Bridge process,
not a sandbox against an operator with filesystem access.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import tempfile
import time
from typing import Any
from uuid import uuid4

from backend.app.application.services.jev_advisor import JevAdvisor, redact
from backend.app.application.services.feedback_validation import (
    FeedbackValidationMixin,
    parse_observations,
)
from backend.app.domain.entities.pipeline_quality import QualityContract


class QualityError(ValueError):
    pass


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PipelineQualityService(FeedbackValidationMixin):
    SNAPSHOT_TIMEOUT_SECONDS = 2.0
    SNAPSHOT_MAX_BYTES = 64 * 1024 * 1024

    def __init__(
        self,
        *,
        database_path: str | Path,
        allowed_roots: list[str | Path],
        advisor: JevAdvisor | None = None,
    ):
        self.database_path = Path(database_path).expanduser().resolve()
        self._roots = [Path(p).expanduser().resolve() for p in allowed_roots]
        self._advisor = advisor or JevAdvisor()

    def scoped(self, allowed_roots: list[str | Path]) -> "PipelineQualityService":
        """Composition-time scope for another trusted runner, sharing the ledger."""
        return PipelineQualityService(
            database_path=self.database_path,
            allowed_roots=allowed_roots,
            advisor=self._advisor,
        )

    @contextmanager
    def _db(self):
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.database_path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute(
                "CREATE TABLE IF NOT EXISTS records (kind TEXT NOT NULL, id TEXT NOT NULL, packet TEXT, created TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(kind,id))"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS records_packet ON records(kind,packet,created)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT UNIQUE NOT NULL, kind TEXT NOT NULL, packet TEXT NOT NULL, created TEXT NOT NULL, payload TEXT NOT NULL)"
            )
            db.commit()
            os.chmod(self.database_path, 0o600)
            with db:
                yield db
        finally:
            db.close()

    def _get(self, kind: str, id: str) -> dict[str, Any]:
        with self._db() as db:
            row = db.execute(
                "SELECT payload FROM records WHERE kind=? AND id=?", (kind, id)
            ).fetchone()
        if row is None:
            raise QualityError(f"Unknown {kind}: {id}")
        return json.loads(row[0])

    def _list(self, kind: str, packet: str | None = None) -> list[dict[str, Any]]:
        with self._db() as db:
            rows = db.execute(
                "SELECT payload FROM records WHERE kind=?"
                + (" AND packet=?" if packet else "")
                + " ORDER BY created,id",
                (kind, packet) if packet else (kind,),
            ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def _put(
        self,
        kind: str,
        data: dict[str, Any],
        *,
        packet: str | None = None,
        event: str | None = None,
    ) -> None:
        with self._db() as db:
            if kind == "lesson":
                # Serialize the immutable insert and comparison across processes.
                db.execute("BEGIN IMMEDIATE")
                row = db.execute(
                    "SELECT payload FROM records WHERE kind=? AND id=?",
                    (kind, data["id"]),
                ).fetchone()
                if row:
                    existing = json.loads(row[0])
                    if any(
                        existing[key] != data[key]
                        for key in (
                            "symptom",
                            "cause_hypothesis",
                            "resolution",
                            "conditions",
                        )
                    ):
                        raise QualityError("A verified lesson is immutable")
                    return
            db.execute(
                "INSERT INTO records VALUES (?,?,?,?,?) ON CONFLICT(kind,id) DO UPDATE SET payload=excluded.payload, packet=excluded.packet",
                (kind, data["id"], packet, data.get("created_at", _now()), _json(data)),
            )
            if event:
                db.execute(
                    "INSERT INTO events(event_id,kind,packet,created,payload) VALUES (?,?,?,?,?)",
                    (str(uuid4()), event, packet or data["id"], _now(), _json(data)),
                )

    def _workspace(self, value: str | Path) -> Path:
        path = Path(value).expanduser().resolve()
        if (
            not any(path.is_relative_to(root) for root in self._roots)
            or not path.is_dir()
        ):
            raise QualityError("Workspace outside configured roots or missing")
        return path

    @contextmanager
    def _workspace_lock(self, workspace: Path):
        lock_root = self.database_path.parent / "quality-locks"
        lock_root.mkdir(parents=True, exist_ok=True)
        with (lock_root / _digest(str(workspace))).open("a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise QualityError(
                    "Another quality operation is running in this workspace"
                ) from None
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def snapshot(self, workspace: str | Path) -> dict[str, str]:
        root = self._workspace(workspace)
        deadline = time.monotonic() + self.SNAPSHOT_TIMEOUT_SECONDS

        def remaining():
            seconds = deadline - time.monotonic()
            if seconds <= 0:
                raise QualityError("Workspace snapshot exceeded time budget")
            return seconds

        def git(*args):
            try:
                result = subprocess.run(
                    ["git", "-C", str(root), *args],
                    capture_output=True,
                    timeout=remaining(),
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise QualityError("Workspace snapshot exceeded time budget") from exc
            if result.returncode:
                raise QualityError(
                    "A Git workspace with a committed baseline is required"
                )
            return result.stdout

        revision = git("rev-parse", "HEAD").decode().strip()
        names = sorted(
            set(
                git(
                    "ls-files", "-z", "--cached", "--others", "--exclude-standard"
                ).split(b"\0")
            )
            - {b""}
        )
        if len(names) > 100_000:
            raise QualityError("Workspace exceeds snapshot file limit")
        digest = hashlib.sha256()
        total_bytes = 0
        for raw in names:
            remaining()
            relative = Path(os.fsdecode(raw))
            # Never read secret contents; Git revision still identifies committed state.
            if any(
                p in {".git", ".data", "secrets", "node_modules", ".venv"}
                for p in relative.parts
            ) or relative.name.startswith(".env"):
                continue
            path = root / relative
            digest.update(raw + b"\0")
            if path.is_symlink():
                digest.update(os.readlink(path).encode())
            elif path.is_file():
                if not path.resolve().is_relative_to(root):
                    raise QualityError("Source file resolves outside workspace")
                if total_bytes + path.stat().st_size > self.SNAPSHOT_MAX_BYTES:
                    raise QualityError("Workspace snapshot exceeded byte budget")
                with path.open("rb") as f:
                    while chunk := f.read(131072):
                        remaining()
                        total_bytes += len(chunk)
                        if total_bytes > self.SNAPSHOT_MAX_BYTES:
                            raise QualityError(
                                "Workspace snapshot exceeded byte budget"
                            )
                        digest.update(chunk)
            else:
                digest.update(b"deleted")
        return {"revision": revision, "source_digest": digest.hexdigest()}

    def register(
        self,
        *,
        workspace: str,
        work_item_id: str,
        contract: dict[str, Any],
        packet_id: str | None = None,
        links: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        root = self._workspace(workspace)
        model = QualityContract.model_validate(contract)
        if not work_item_id.strip() or len(work_item_id) > 200:
            raise QualityError("Work item ID is required")
        for check in model.checks:
            target = (root / check.cwd).resolve()
            if not target.is_relative_to(root) or not target.is_dir():
                raise QualityError("Check directory must exist inside workspace")
        data = model.model_dump()
        if redact(_json(data)) != _json(data):
            raise QualityError(
                "Keep credentials out of contracts and command arguments"
            )
        id = packet_id or "quality-" + _digest([str(root), work_item_id])[:24]
        if id in data["dependencies"]:
            raise QualityError("A packet cannot depend on itself")
        packet = {
            "id": id,
            "workspace": str(root),
            "work_item_id": work_item_id,
            "contract": data,
            "contract_digest": _digest(data),
            "created_at": _now(),
            "links": links or {},
            "lifecycle": "active",
        }
        with self._workspace_lock(root):
            try:
                previous = self._get("packet", id)
            except QualityError:
                previous = None
            if previous:
                if (
                    previous["workspace"] != str(root)
                    or previous["work_item_id"] != work_item_id
                ):
                    raise QualityError("Packet identity cannot be rebound")
                if (
                    previous["contract_digest"] == packet["contract_digest"]
                    and previous["links"] == packet["links"]
                ):
                    return previous
                packet["created_at"] = previous["created_at"]
            self._put("packet", packet, packet=id, event="quality.contract_registered")
        return packet

    def register_file(
        self, *, workspace: str, work_item_id: str, links: dict[str, str] | None = None
    ) -> dict[str, Any]:
        root = self._workspace(workspace)
        path = root / ".codex/quality.json"
        if (
            not path.is_file()
            or not path.resolve().is_relative_to(root)
            or path.stat().st_size > 100_000
        ):
            raise QualityError(
                "Create .codex/quality.json with criteria and executable checks first"
            )
        return self.register(
            workspace=str(root),
            work_item_id=work_item_id,
            contract=json.loads(path.read_text()),
            links=links,
        )

    def packets(self) -> list[dict[str, Any]]:
        return [
            packet
            for packet in self._list("packet")
            if any(
                Path(packet["workspace"]).resolve().is_relative_to(root)
                for root in self._roots
            )
        ]

    def status(
        self, packet_id: str, *, _visited: set[str] | None = None
    ) -> dict[str, Any]:
        packet = self._get("packet", packet_id)
        visited = set(_visited or ())
        if packet_id in visited:
            raise QualityError("Dependency cycle")
        visited.add(packet_id)
        contract = packet["contract"]
        snapshot_error = None
        try:
            snapshot = self.snapshot(packet["workspace"])
        except (QualityError, OSError) as exc:
            # An unavailable snapshot must never validate old receipts or stop
            # chat/reviewer context from being delivered.
            snapshot = None
            snapshot_error = str(exc)
        receipts = self._list("receipt", packet_id)
        current = [
            r
            for r in receipts
            if snapshot is not None
            and r["contract_digest"] == packet["contract_digest"]
            and r["source"] == snapshot
        ]
        latest = {r["check_id"]: r for r in current}
        blockers = (
            ["packet_superseded"] if packet.get("lifecycle") == "superseded" else []
        )
        if snapshot_error:
            blockers.append("source_snapshot_unavailable")
        criteria = []
        for criterion in contract["criteria"]:
            state = "verified"
            if criterion["decision_pending"]:
                state = "blocked"
            elif not criterion["check_ids"]:
                state = "unverified"
            elif any(
                latest.get(id, {}).get("status")
                in {"failed", "timeout", "error", "interrupted", "stale"}
                for id in criterion["check_ids"]
            ):
                state = "failed"
            elif any(
                latest.get(id, {}).get("status") != "passed"
                for id in criterion["check_ids"]
            ):
                state = "unverified"
            criteria.append(
                {
                    **criterion,
                    "status": state,
                    "receipt_ids": [
                        latest[id]["id"]
                        for id in criterion["check_ids"]
                        if id in latest
                    ],
                }
            )
            if state != "verified":
                blockers.append(f"criterion:{criterion['id']}:{state}")
        for check in contract["checks"]:
            if (
                check["required"]
                and latest.get(check["id"], {}).get("status") != "passed"
            ):
                blockers.append(f"check:{check['id']}:not_passed")
        for dependency in contract["dependencies"]:
            try:
                satisfied = self.status(dependency, _visited=visited)["verified"]
                if satisfied:
                    satisfied = not self.feedback_packet_blockers(dependency)
            except QualityError:
                satisfied = False
            if not satisfied:
                blockers.append(f"dependency:{dependency}:not_verified")
        return {
            **packet,
            "source": snapshot,
            "source_error": snapshot_error,
            "verified": not blockers,
            "criteria": criteria,
            "blockers": blockers,
            "receipt_count": len(receipts),
            "current_receipts": list(latest.values()),
            "acceptance_scope": "Registered executable criteria only; not commercial acceptance or deployment approval",
        }

    def execute(
        self, packet_id: str, *, attempt_key: str, check_ids: list[str] | None = None
    ) -> dict[str, Any]:
        if not attempt_key.strip() or len(attempt_key) > 160:
            raise QualityError("An attempt idempotency key is required")
        packet = self._get("packet", packet_id)
        root = self._workspace(packet["workspace"])
        with self._workspace_lock(root):
            packet = self._get("packet", packet_id)
            contract = packet["contract"]
            checks = contract["checks"]
            if check_ids is not None:
                if not check_ids or set(check_ids) - {x["id"] for x in checks}:
                    raise QualityError("Select registered check IDs")
                checks = [x for x in checks if x["id"] in check_ids]
            if not checks:
                raise QualityError("No executable checks registered")
            source = self.snapshot(root)
            attempt_id = "attempt-" + _digest([packet_id, attempt_key])[:24]
            try:
                existing = self._get("attempt", attempt_id)
            except QualityError:
                existing = None
            if existing:
                if (
                    existing["source"] != source
                    or existing["contract_digest"] != packet["contract_digest"]
                    or existing["check_ids"] != [x["id"] for x in checks]
                ):
                    raise QualityError(
                        "Attempt key already belongs to a different revision, contract or selection"
                    )
                if existing["status"] == "running":
                    # Acquiring the workspace lock means no live runner owns this attempt.
                    existing["status"] = "interrupted"
                    existing["finished_at"] = _now()
                    self._put(
                        "attempt",
                        existing,
                        packet=packet_id,
                        event="quality.attempt_interrupted",
                    )
                return existing
            attempts = self._list("attempt", packet_id)
            if len(attempts) >= contract["max_attempts"]:
                raise QualityError(
                    "Repair attempt limit reached; inspect evidence before creating another work item"
                )
            for dependency in contract["dependencies"]:
                if not self.status(dependency)["verified"]:
                    raise QualityError("Required dependency is not verified")
            if any(x["decision_pending"] for x in contract["criteria"]):
                raise QualityError(
                    "Resolve the recorded product decision before execution"
                )
            attempt = {
                "id": attempt_id,
                "packet_id": packet_id,
                "source": source,
                "contract_digest": packet["contract_digest"],
                "check_ids": [x["id"] for x in checks],
                "created_at": _now(),
                "status": "running",
                "receipt_ids": [],
            }
            self._put(
                "attempt", attempt, packet=packet_id, event="quality.attempt_started"
            )
            start = time.monotonic()
            try:
                for check in checks:
                    receipt = self._run_check(packet, attempt_id, check, source)
                    attempt["receipt_ids"].append(receipt["id"])
            except BaseException:
                attempt.update(status="interrupted", finished_at=_now())
                self._put(
                    "attempt",
                    attempt,
                    packet=packet_id,
                    event="quality.attempt_interrupted",
                )
                raise
            attempt.update(
                status="completed",
                finished_at=_now(),
                duration_ms=round((time.monotonic() - start) * 1000, 2),
            )
            self._put(
                "attempt", attempt, packet=packet_id, event="quality.attempt_completed"
            )
        return {
            **attempt,
            "quality": self.status(packet_id),
            "diagnosis": self.diagnose(packet_id),
            "feedback_validation": self.evaluate_packet_feedback(packet_id),
        }

    def _run_check(
        self,
        packet: dict[str, Any],
        attempt_id: str,
        check: dict[str, Any],
        source: dict[str, str],
    ) -> dict[str, Any]:
        root = Path(packet["workspace"])
        target = (root / check["cwd"]).resolve()
        if not target.is_relative_to(root) or not target.is_dir():
            raise QualityError("Check directory changed or escaped workspace")
        receipt = {
            "id": "receipt-" + str(uuid4()),
            "packet_id": packet["id"],
            "attempt_id": attempt_id,
            "project_id": packet["contract"]["project_id"],
            "environment": packet["contract"]["environment"],
            "contract_digest": packet["contract_digest"],
            "check_id": check["id"],
            "source": source,
            "command_digest": _digest(check),
            "created_at": _now(),
            "status": "running",
            "provenance": "bridge-quality-subprocess-v1",
        }
        self._put(
            "receipt", receipt, packet=packet["id"], event="quality.check_started"
        )
        env = {
            key: value
            for key, value in os.environ.items()
            if key
            in {"PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "VIRTUAL_ENV", "SYSTEMROOT"}
        }
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        started = time.monotonic()
        with tempfile.TemporaryFile() as output:
            try:
                process = subprocess.Popen(
                    check["argv"],
                    cwd=target,
                    env=env,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    shell=False,
                    start_new_session=True,
                )
                try:
                    deadline = time.monotonic() + check["timeout_seconds"]
                    while process.poll() is None:
                        if (
                            time.monotonic() >= deadline
                            or os.fstat(output.fileno()).st_size > 10_000_000
                        ):
                            raise subprocess.TimeoutExpired(
                                check["argv"], check["timeout_seconds"]
                            )
                        time.sleep(0.05)
                    receipt["exit_code"] = process.returncode
                    receipt["status"] = (
                        "passed" if receipt["exit_code"] == 0 else "failed"
                    )
                except subprocess.TimeoutExpired:
                    receipt.update(status="timeout", exit_code=None)
                except BaseException:
                    receipt.update(
                        status="interrupted", exit_code=None, finished_at=_now()
                    )
                    self._put(
                        "receipt",
                        receipt,
                        packet=packet["id"],
                        event="quality.check_interrupted",
                    )
                    raise
                finally:
                    if process.poll() is None:
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        process.wait()
            except OSError:
                receipt.update(status="error", exit_code=None)
            output.seek(0, os.SEEK_END)
            receipt["output_bytes"] = output.tell()
            output.seek(max(0, output.tell() - 12000))
            receipt["output_excerpt"] = redact(output.read().decode(errors="replace"))
            receipt["observations"] = parse_observations(receipt["output_excerpt"])
        try:
            after = self.snapshot(root)
        except (QualityError, OSError, subprocess.SubprocessError):
            after = None
        if after != source:
            receipt["status"] = "stale"
        receipt.update(
            finished_at=_now(),
            duration_ms=round((time.monotonic() - started) * 1000, 2),
            source_after=after,
            output_digest=_digest(receipt["output_excerpt"]),
        )
        self._put(
            "receipt", receipt, packet=packet["id"], event="quality.check_finished"
        )
        return receipt

    def diagnose(self, packet_id: str) -> dict[str, Any]:
        packet = self._get("packet", packet_id)
        receipts = self._list("receipt", packet_id)
        failures = [
            r for r in receipts if r["status"] in {"failed", "timeout", "error"}
        ]
        if not failures:
            return {"status": "no_failure", "advisory_only": True}
        current = failures[-1]
        if any(
            r["check_id"] == current["check_id"]
            and r["created_at"] > current["created_at"]
            and r["status"] == "passed"
            for r in receipts
        ):
            return {
                "status": "failure_has_later_passing_check",
                "advisory_only": True,
                "note": "Current acceptance still depends on source identity and all required criteria",
            }
        id = "diagnosis-" + current["id"]
        try:
            return self._get("diagnosis", id)
        except QualityError:
            pass
        # Compare consecutive results for the same check, not two failures separated by a pass.
        prior = [
            r
            for r in receipts
            if r["check_id"] == current["check_id"]
            and r["created_at"] < current["created_at"]
        ]
        previous = prior[-1] if prior else None
        same = bool(
            previous
            and previous["status"] == current["status"]
            and previous.get("output_digest") == current.get("output_digest")
            and previous.get("exit_code") == current.get("exit_code")
        )
        candidates = self.lessons_for(packet_id)
        linked_items = {c["feedback_item_id"] for c in packet["contract"]["criteria"]}
        feedback_input = any(
            request["project_id"] == packet["contract"]["project_id"]
            and request["feedback_item_id"] in linked_items
            for request in self.feedback_requests(packet["workspace"])
        )
        # The new feedback policy permits minimized facts, not implicit log sharing
        # through the pre-existing diagnostic hook run after a failed subprocess.
        advice = (
            {"status": "disabled", "reason": "feedback_uses_minimized_fulfillment_only"}
            if feedback_input
            else self._advisor.advise(
                failure=current.get("output_excerpt", ""),
                previous_failure=previous.get("output_excerpt", "") if previous else "",
                lessons=candidates,
            )
        )
        diagnosis = {
            "id": id,
            "packet_id": packet_id,
            "created_at": _now(),
            "receipt_id": current["id"],
            "status": "needs_diagnosis",
            "same_failure_signature": same,
            "stalled": same,
            "next_action": "change_diagnostic_or_escalate"
            if same
            else "reproduce_and_inspect",
            "candidate_lesson_ids": [x["id"] for x in candidates],
            "advice": advice,
            "advisory_only": True,
        }
        self._put("diagnosis", diagnosis, packet=packet_id, event="quality.diagnosis")
        return diagnosis

    def save_lesson(
        self,
        *,
        packet_id: str,
        failed_receipt_id: str,
        passed_receipt_id: str,
        symptom: str,
        cause_hypothesis: str,
        resolution: str,
        conditions: str,
    ) -> dict[str, Any]:
        packet = self._get("packet", packet_id)
        failed = self._get("receipt", failed_receipt_id)
        passed = self._get("receipt", passed_receipt_id)
        if (
            failed["packet_id"] != packet_id
            or passed["packet_id"] != packet_id
            or failed["status"] != "failed"
            or passed["status"] != "passed"
            or failed["check_id"] != passed["check_id"]
            or failed["command_digest"] != passed["command_digest"]
            or failed["created_at"] >= passed["created_at"]
            or failed["source"] == passed["source"]
        ):
            raise QualityError(
                "A lesson needs a failure followed by a passing execution of the same check after a change"
            )
        current = self.status(packet_id)
        if not current["verified"] or passed["id"] not in {
            x["id"] for x in current["current_receipts"]
        }:
            raise QualityError(
                "The packet and passing receipt must still be verified for the current source"
            )
        for text in (symptom, cause_hypothesis, resolution, conditions):
            if not text.strip() or len(text) > 4000:
                raise QualityError("Lesson fields must contain 1–4000 characters")
        lesson = {
            "id": "lesson-" + _digest([failed_receipt_id, passed_receipt_id])[:24],
            "packet_id": packet_id,
            "project_id": packet["contract"]["project_id"],
            "component_ids": packet["contract"]["component_ids"],
            "created_at": _now(),
            "status": "verified_repair",
            "failed_receipt_id": failed_receipt_id,
            "passed_receipt_id": passed_receipt_id,
            "symptom": redact(symptom),
            "cause_hypothesis": redact(cause_hypothesis),
            "resolution": redact(resolution),
            "conditions": redact(conditions),
            "source": passed["source"],
            "scope": "Observed repair; the supplied causal explanation remains a hypothesis",
        }
        try:
            existing = self._get("lesson", lesson["id"])
        except QualityError:
            existing = None
        if existing:
            if any(
                existing[key] != lesson[key]
                for key in ("symptom", "cause_hypothesis", "resolution", "conditions")
            ):
                raise QualityError(
                    "A verified lesson is immutable; create a new evidenced repair"
                )
            return existing
        self._put("lesson", lesson, packet=packet_id, event="quality.lesson_verified")
        return lesson

    def lessons_for(self, packet_id: str) -> list[dict[str, Any]]:
        contract = self._get("packet", packet_id)["contract"]
        return [
            x
            for x in reversed(self._list("lesson"))
            if x["project_id"] == contract["project_id"]
            or set(x["component_ids"]) & set(contract["component_ids"])
        ][:20]

    def feedback_resolution(
        self, *, source_app: str, item_ids: list[str], workspace: str | None
    ) -> dict[str, Any]:
        items = {
            id: {
                "item_id": id,
                "status": "unverified",
                "packet_id": None,
                "receipt_ids": [],
                "blockers": [],
            }
            for id in item_ids
        }
        bindings: dict[str, list[dict[str, Any]]] = {id: [] for id in item_ids}
        if workspace:
            for packet in self.packets():
                if (
                    packet["workspace"] != str(Path(workspace).resolve())
                    or packet["contract"]["project_id"] != source_app
                ):
                    continue
                try:
                    state = self.status(packet["id"])
                except (QualityError, OSError, subprocess.SubprocessError):
                    continue
                dependency_blockers = [
                    blocker
                    for blocker in state["blockers"]
                    if blocker.startswith("dependency:")
                ]
                for criterion in state["criteria"]:
                    id = criterion.get("feedback_item_id")
                    if id in items:
                        bindings[id].append(
                            {
                                **criterion,
                                "packet_id": packet["id"],
                                "status": "blocked"
                                if dependency_blockers
                                and criterion["status"] == "verified"
                                else criterion["status"],
                                "blockers": dependency_blockers,
                            }
                        )
        for id, criteria in bindings.items():
            if criteria:
                states = {c["status"] for c in criteria}
                status = (
                    "verified"
                    if states == {"verified"}
                    else "failed"
                    if "failed" in states
                    else "blocked"
                    if "blocked" in states
                    else "unverified"
                )
                items[id] = {
                    "item_id": id,
                    "status": status,
                    "packet_id": criteria[-1]["packet_id"],
                    "receipt_ids": list(
                        dict.fromkeys(r for c in criteria for r in c["receipt_ids"])
                    ),
                    "blockers": list(
                        dict.fromkeys(b for c in criteria for b in c["blockers"])
                    ),
                }
        improvements = []
        if workspace:
            try:
                requests = self.feedback_requests(workspace)
            except ValueError:
                requests = []  # Historical batches may reference a removed workspace.
            for request in requests:
                if request["project_id"] != source_app or not set(
                    request["item_ids"]
                ) & set(item_ids):
                    continue
                verdict = self.feedback_verdict(request["id"])
                improvements.append(verdict)
                for alias in request["item_ids"]:
                    if alias in items:
                        items[alias].update(
                            status="verified" if verdict["verified"] else "unverified",
                            verdict=verdict["verdict"],
                            blockers=verdict["blockers"],
                            request_id=request["id"],
                        )
        verified = sum(x["status"] == "verified" for x in items.values())
        return {
            "status": "verified"
            if items and verified == len(items)
            else "pending_verification",
            "verified_count": verified,
            "item_count": len(items),
            "items": list(items.values()),
            "improvements": improvements,
            "validation_summary": {
                "total": len(improvements),
                "fulfilled": sum(x["verified"] for x in improvements),
                "pending": sum(not x["verified"] for x in improvements),
            },
        }

    def stage_gate(self, workspace: str, stage_id: str) -> dict[str, Any]:
        packets = [
            p
            for p in self.packets()
            if p["workspace"] == str(Path(workspace).resolve())
            and p["links"].get("stage_id") == stage_id
            and p.get("lifecycle") != "superseded"
        ]
        if not packets:
            return {
                "enrolled": False,
                "verified": False,
                "blockers": ["quality_contract_missing"],
            }
        states = [self.status(p["id"]) for p in packets]
        pending_feedback = []
        for request in self.active_acceptance_requests(workspace):
            verdict = self.feedback_verdict(request["id"])
            linked = (
                self._get("packet", verdict["packet_id"])
                if verdict.get("packet_id")
                else None
            )
            if linked and linked.get("lifecycle") == "closed":
                continue
            if not verdict["verified"]:
                pending_feedback.append("feedback:" + request["id"] + ":not_verified")
        return {
            "enrolled": True,
            "verified": all(x["verified"] for x in states) and not pending_feedback,
            "packet_ids": [p["id"] for p in packets],
            "blockers": [b for x in states for b in x["blockers"]] + pending_feedback,
        }

    def reviewer_context(self, workspace: str) -> str | None:
        feedback = self.feedback_validation_context(workspace)
        packets = [
            p
            for p in self.packets()
            if p["workspace"] == str(Path(workspace).resolve())
            and p.get("lifecycle", "active") == "active"
        ]
        if not packets:
            return feedback
        states = [self.status(p["id"]) for p in packets[-5:]]
        payload = [
            {
                "packet_id": x["id"],
                "work_item_id": x["work_item_id"],
                "source": x["source"],
                "criteria": x["criteria"],
                "blockers": x["blockers"],
            }
            for x in states
        ]
        return (
            "Independent verification input. Derive expectations from these registered criteria and inspect the actual source and runner evidence. Missing evidence is not success. Do not rewrite criteria to match the implementation.\n"
            + _json(payload)
            + ("\n\n" + feedback if feedback else "")
        )

    def gestion_payload(self, packet_id: str, project_id: str) -> dict[str, Any]:
        state = self.status(packet_id)
        feedback_blockers = self.feedback_packet_blockers(packet_id)
        state["blockers"] += feedback_blockers
        state["verified"] = state["verified"] and not feedback_blockers
        observation = {
            "packet_id": packet_id,
            "project_id": state["contract"]["project_id"],
            "work_item_id": state["work_item_id"],
            "environment": state["contract"]["environment"],
            "source": state["source"],
            "contract_digest": state["contract_digest"],
            "verified": state["verified"],
            "criteria": state["criteria"],
            "blockers": state["blockers"],
        }
        observation_id = "current-observation-" + packet_id
        # Compare the latest capture, not all historical hashes: A -> B -> A
        # needs a fresh sequence even when A was previously observed.
        with self._workspace_lock(self._workspace(state["workspace"])):
            try:
                previous = self._get("observation", observation_id)
            except QualityError:
                previous = None
            if previous is None or previous["digest"] != _digest(observation):
                self._put(
                    "observation",
                    {
                        "id": observation_id,
                        "created_at": _now(),
                        "digest": _digest(observation),
                        **observation,
                    },
                    packet=packet_id,
                    event="quality.observation_captured",
                )
            with self._db() as db:
                sequence = db.execute(
                    "SELECT MAX(sequence) FROM events WHERE packet=?", (packet_id,)
                ).fetchone()[0]
        export = self.export(limit=1)
        return {
            "projectId": project_id,
            "producerId": export["producer_id"],
            "sequence": sequence,
            "observation": observation,
        }

    def repair_context(self, workspace: str) -> str | None:
        feedback = self.feedback_validation_context(workspace, pending_only=True)
        packets = [
            p
            for p in self.packets()
            if p["workspace"] == str(Path(workspace).resolve())
            and p.get("lifecycle", "active") == "active"
        ]
        if not packets:
            return feedback
        items = []
        for packet in packets[-5:]:
            state = self.status(packet["id"])
            if state["verified"]:
                continue
            diagnoses = self._list("diagnosis", packet["id"])
            items.append(
                {
                    "packet_id": packet["id"],
                    "blockers": state["blockers"],
                    "diagnosis": diagnoses[-1] if diagnoses else None,
                    "candidate_lessons": self.lessons_for(packet["id"])[:3],
                }
            )
        if not items:
            return feedback
        return (
            "Required quality work remains. Reproduce and inspect before repairing; "
            "do not repeat an identical repair when the signature is unchanged. Lessons are conditional, "
            "and suggested causes are hypotheses. Execute the registered checks again after the change.\n"
            + _json(items)
            + ("\n\n" + feedback if feedback else "")
        )

    def close(self, packet_id: str) -> dict[str, Any]:
        packet = self._get("packet", packet_id)
        with self._workspace_lock(Path(packet["workspace"])):
            state = self.status(packet_id)
            if not state["verified"]:
                raise QualityError(
                    "Only currently verified work can leave the active repair queue"
                )
            if self.feedback_packet_blockers(packet_id) or any(
                not self.feedback_verdict(plan["id"])["verified"]
                for plan in self._list("feedback_plan", packet_id)
            ):
                raise QualityError(
                    "Feedback acceptance still has missing or negative evidence"
                )
            if packet.get("lifecycle") != "closed":
                packet.update(
                    lifecycle="closed", closed_at=_now(), closed_source=state["source"]
                )
                self._put(
                    "packet", packet, packet=packet_id, event="quality.work_closed"
                )
        return packet

    def export(self, *, after: int = 0, limit: int = 100) -> dict[str, Any]:
        with self._db() as db:
            db.execute(
                "INSERT OR IGNORE INTO records VALUES ('meta','producer',NULL,?,?)",
                (_now(), _json({"id": str(uuid4())})),
            )
            producer = json.loads(
                db.execute(
                    "SELECT payload FROM records WHERE kind='meta' AND id='producer'"
                ).fetchone()[0]
            )["id"]
            rows = db.execute(
                "SELECT sequence,event_id,kind,packet,created FROM events WHERE sequence>? ORDER BY sequence LIMIT ?",
                (max(0, after), min(max(1, limit), 500)),
            ).fetchall()
        events = [dict(r) for r in rows]
        # Intake has an event before a work packet exists; it must not create a
        # phantom work item (or masquerade as a missing source) in the projection.
        ids = list(
            dict.fromkeys(
                x["packet"]
                for x in events
                if x["kind"]
                not in {
                    "feedback.request_captured",
                    "quality.requirement_captured",
                    "quality.source_captured",
                    "quality.requirement_superseded",
                }
            )
        )
        states = []
        for id in ids:
            try:
                state = self.status(id)
                feedback_blockers = self.feedback_packet_blockers(id)
                state["blockers"] += feedback_blockers
                state["verified"] = state["verified"] and not feedback_blockers
                states.append(
                    {
                        "packet_id": id,
                        "project_id": state["contract"]["project_id"],
                        "work_item_id": state["work_item_id"],
                        "environment": state["contract"]["environment"],
                        "source": state["source"],
                        "contract_digest": state["contract_digest"],
                        "verified": state["verified"],
                        "criteria": state["criteria"],
                        "blockers": state["blockers"],
                    }
                )
            except (QualityError, OSError, subprocess.SubprocessError):
                states.append(
                    {
                        "packet_id": id,
                        "verified": False,
                        "blockers": ["source_unavailable"],
                    }
                )
        return {
            "schema": "nienfos.pipeline-evidence/v1",
            "generated_at": _now(),
            "producer_id": producer,
            "next_cursor": events[-1]["sequence"] if events else after,
            "events": events,
            "work_items": states,
            "policy": "Operational evidence only. Does not update commercial commitments, approve releases or send messages.",
        }
