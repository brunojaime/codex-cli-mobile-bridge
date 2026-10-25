"""Chat sources, explicit requirement revisions and evidence-bound manual retests."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shlex
from uuid import uuid4

from backend.app.application.services.jev_advisor import redact
from backend.app.domain.entities.requirement_validation import (
    ManualAcceptanceReview,
    RequirementFromSource,
    RequirementRevision,
)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


class AcceptanceWorkflowMixin:
    def chat_intake_context(self, *, workspace, source_ref, text):
        try:
            root = self._workspace(workspace)
        except ValueError:
            return None
        bridge = Path(__file__).resolve().parents[4]
        cli = " ".join(
            shlex.quote(str(p))
            for p in (
                bridge / ".venv/bin/python",
                bridge / "scripts/pipeline_quality.py",
            )
        )
        cli += " --database " + shlex.quote(str(self.database_path))
        # Do not silently truncate a long specification or attachment transcript.
        if not 1 <= len(text) <= 10000:
            return (
                "Acceptance intake: this message exceeds the source intake limit. Read the full original and register explicit requirements with source references using "
                + cli
                + " register-requirement. Do not claim automatic source capture or silently omit scope."
            )
        source = {
            "id": "source-" + _digest([str(root), source_ref])[:24],
            "workspace": str(root),
            "source_ref": source_ref,
            "text": redact(text),
            "created_at": _now(),
        }
        # Intake must remain available while a check holds the workspace runner
        # lock. Serialize this immutable append in SQLite, not against execution.
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT payload FROM records WHERE kind='requirement_source' AND id=?",
                (source["id"],),
            ).fetchone()
            existing = json.loads(row[0]) if row else None
            if existing and existing["text"] != source["text"]:
                raise ValueError("Chat source is immutable")
            if not existing:
                serialized = json.dumps(source, ensure_ascii=False)
                db.execute(
                    "INSERT INTO records VALUES (?,?,?,?,?)",
                    (
                        "requirement_source",
                        source["id"],
                        None,
                        source["created_at"],
                        serialized,
                    ),
                )
                db.execute(
                    "INSERT INTO events(event_id,kind,packet,created,payload) VALUES (?,?,?,?,?)",
                    (
                        str(uuid4()),
                        "quality.source_captured",
                        source["id"],
                        _now(),
                        serialized,
                    ),
                )
        return (
            "Acceptance intake for this human message. Source ID: "
            + source["id"]
            + ". "
            "If the user requests new implementation, derive explicit criteria and register the requirement BEFORE editing code with "
            + cli
            + " requirement-from-source "
            + source["id"]
            + " --file CRITERIA.json. "
            "The file contains requirement_id, project_id, environment and criteria (id, description); the server preserves the original text. "
            "Do not register questions/status requests as new work. If feedback already has an acceptance request, reuse it. "
            "For an amendment inspect existing requirements and use revise-requirement with the user's decision_ref; never silently replace scope. "
            "Read docs/acceptance-workflow.md in the Bridge checkout. Implement, run the registered checks and report evidence per request. "
            "If DEV publication is not authorized, stop at local evidence and report deployed verification as pending. "
            "Jev gets only approved minimized facts. A model opinion cannot substitute executed tests."
        )

    def requirement_sources(self, workspace):
        root = str(self._workspace(workspace))
        return [s for s in self._list("requirement_source") if s["workspace"] == root]

    def requirement_from_source(self, source_id, payload):
        source = self._get("requirement_source", source_id)
        fields = RequirementFromSource.model_validate(payload).model_dump()
        return self.register_requirement(
            workspace=source["workspace"],
            definition={
                **fields,
                "text": source["text"],
                "source_ref": source["source_ref"],
            },
        )

    def request_replacement(self, request_id):
        try:
            return self._get("request_supersession", request_id)["replacement_id"]
        except ValueError:
            return None

    def acceptance_history(self, request_id):
        request = self._get("feedback_request", request_id)
        self._workspace(request["workspace"])
        return {
            "request": request,
            "revisions": [
                r
                for r in self._list("request_supersession")
                if r["id"] == request_id or r["replacement_id"] == request_id
            ],
            "manual_reviews": [
                r
                for r in self._list("manual_acceptance_review")
                if r["request_id"] == request_id
            ],
        }

    def active_acceptance_requests(self, workspace):
        retired = {r["id"] for r in self._list("request_supersession")}
        return [r for r in self.feedback_requests(workspace) if r["id"] not in retired]

    def _write_workflow_records(self, records):
        """One SQLite transaction for graph changes and their audit events."""
        with self._db() as db:
            for kind, payload, packet, event in records:
                serialized = json.dumps(payload, ensure_ascii=False, allow_nan=False)
                db.execute(
                    "INSERT INTO records VALUES (?,?,?,?,?) ON CONFLICT(kind,id) DO UPDATE SET payload=excluded.payload, packet=excluded.packet",
                    (
                        kind,
                        payload["id"],
                        packet,
                        payload.get("created_at", _now()),
                        serialized,
                    ),
                )
                db.execute(
                    "INSERT INTO events(event_id,kind,packet,created,payload) VALUES (?,?,?,?,?)",
                    (str(uuid4()), event, packet or payload["id"], _now(), serialized),
                )

    def revise_requirement(self, request_id, payload):
        revision = RequirementRevision.model_validate(payload).model_dump()
        old = self._get("feedback_request", request_id)
        root, replacement = self._prepare_requirement(
            workspace=old["workspace"], definition=revision["definition"]
        )
        if (
            old.get("origin") != "requirement"
            or any(replacement[k] != old[k] for k in ("project_id", "environment"))
            or replacement["id"] == request_id
        ):
            raise ValueError(
                "A revision needs a new requirement ID in the same project and environment"
            )
        decision = {
            "id": request_id,
            "replacement_id": replacement["id"],
            "reason": redact(revision["reason"]),
            "decision_ref": redact(revision["decision_ref"]),
            "created_at": _now(),
        }
        with self._workspace_lock(root):
            if self.request_replacement(request_id):
                existing = self._get("request_supersession", request_id)
                if (
                    all(
                        existing[k] == decision[k]
                        for k in ("replacement_id", "reason", "decision_ref")
                    )
                    and self._get("feedback_request", replacement["id"])[
                        "request_digest"
                    ]
                    == replacement["request_digest"]
                ):
                    return existing
                raise ValueError(
                    "Requirement already superseded by another explicit decision"
                )
            if any(r["id"] == replacement["id"] for r in self.feedback_requests(root)):
                raise ValueError(
                    "Replacement must be a new immutable requirement; cycles are not allowed"
                )
            writes = [
                ("feedback_request", replacement, None, "quality.requirement_captured"),
                (
                    "request_supersession",
                    decision,
                    None,
                    "quality.requirement_superseded",
                ),
            ]
            for packet in self.packets():
                if (
                    packet["workspace"] != str(root)
                    or packet["contract"]["project_id"] != old["project_id"]
                ):
                    continue
                links = {c["feedback_item_id"] for c in packet["contract"]["criteria"]}
                if links == {old["feedback_item_id"]}:
                    packet.update(
                        lifecycle="superseded", superseded_by=replacement["id"]
                    )
                    writes.append(
                        ("packet", packet, packet["id"], "quality.packet_superseded")
                    )
            self._write_workflow_records(writes)
        return decision

    def _with_manual_review(self, request, result):
        result["technical_verified"] = result["verified"]
        reviews = [
            r
            for r in self._list("manual_acceptance_review")
            if r["request_id"] == request["id"]
        ]
        result["human_review"] = {
            "status": "pending_retest",
            "attribution": "operator_recorded",
        }
        open_failure = False
        for review in reviews:
            if review["outcome"] == "still_failing":
                open_failure = True
            elif review["outcome"] == "confirmed":
                open_failure = False
        if reviews:
            last = reviews[-1]
            current = last["evidence_key"] == result.get("evidence_key")
            result["human_review"] = {
                **last,
                "status": last["outcome"] if current else "pending_retest",
                "attribution": "operator_recorded",
                "evidence_current": current,
            }
        if open_failure:
            result["verified"] = False
            result["verdict"] = "not_fulfilled"
            result["blockers"].append("human_retest_required")
        return result

    def record_manual_review(self, request_id, payload):
        review = ManualAcceptanceReview.model_validate(payload).model_dump()
        request = self._get("feedback_request", request_id)
        with self._workspace_lock(self._workspace(request["workspace"])):
            result = self.feedback_verdict(request_id)
            if (
                result.get("lifecycle") == "superseded"
                or result.get("evidence_key") != review["evidence_key"]
            ):
                raise ValueError(
                    "Review does not match current request and evidence; refresh before retesting"
                )
            if review["outcome"] == "confirmed" and not result.get(
                "technical_verified"
            ):
                raise ValueError(
                    "Manual confirmation cannot replace missing or failed technical evidence"
                )
            if result.get("scope") == "deployed" and review.get(
                "observed_target"
            ) != result.get("target"):
                raise ValueError(
                    "Manual retest must identify the same environment, origin and release"
                )
            record = {
                **review,
                "id": "review-" + str(uuid4()),
                "request_id": request_id,
                "created_at": _now(),
                "target": result.get("target"),
                "note": redact(review["note"]),
                "decision_ref": redact(review["decision_ref"]),
                "actor_label": redact(review["actor_label"]),
            }
            writes = [
                (
                    "manual_acceptance_review",
                    record,
                    result["packet_id"],
                    "quality.manual_retest",
                )
            ]
            if review["outcome"] == "still_failing":
                packet = self._get("packet", result["packet_id"])
                packet["lifecycle"] = "active"
                writes.append(("packet", packet, packet["id"], "quality.work_reopened"))
            self._write_workflow_records(writes)
        return record
