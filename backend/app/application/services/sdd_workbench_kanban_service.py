from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from backend.app.application.services.project_factory_service import (
    ProjectFactoryService,
)
from backend.app.application.services.sdd_project_service import (
    SddProject,
    SddSpec,
)
from backend.app.application.services.sdd_standard_service import (
    SddStandardError,
    parse_simple_yaml,
)


KANBAN_COLUMN_ORDER = (
    "backlog",
    "ready",
    "in_progress",
    "review",
    "blocked",
    "done",
)

KANBAN_COLUMN_LABELS = {
    "backlog": "Backlog",
    "ready": "Ready",
    "in_progress": "In Progress",
    "review": "Review",
    "blocked": "Blocked",
    "done": "Done",
}

_TASK_LINE_RE = re.compile(
    r"^\s*[-*]\s+\[(?P<mark>[ xX])\]\s+(?P<task>T\d{3,4})\b[:.\-\s]*(?P<title>.*)$"
)
_TASK_ID_RE = re.compile(r"\b(T\d{3,4})\b")
_HISTORY_LIMIT = 80
_POLL_INTERVAL_SECONDS = 30


@dataclass(frozen=True, slots=True)
class SddWorkbenchKanbanResult:
    payload: dict[str, Any]
    storage_root: Path


class SddWorkbenchKanbanService:
    """Read-only deterministic projection for Workbench Kanban state."""

    def __init__(
        self,
        *,
        projects_root: str | Path,
        project_factory_service: ProjectFactoryService | None = None,
    ) -> None:
        self._projects_root = Path(projects_root).expanduser().resolve()
        self._project_factory_service = project_factory_service

    def build_board(
        self,
        *,
        workspace: Path | None = None,
        project: SddProject | None = None,
        spec_id: str | None = None,
        draft_id: str | None = None,
        job_id: str | None = None,
        force_refresh: bool = False,
    ) -> SddWorkbenchKanbanResult:
        now = _now_iso()
        scope = self._scope_payload(
            workspace=workspace,
            project=project,
            spec_id=spec_id,
            draft_id=draft_id,
            job_id=job_id,
        )
        storage_root = self._storage_root(workspace=workspace, scope=scope)
        storage_root.mkdir(parents=True, exist_ok=True)
        previous = _read_json(storage_root / "board-cache.json")

        cards: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        continuity: list[dict[str, Any]] = []
        if project is not None and workspace is not None:
            sdd_cards, sdd_evidence = _project_cards(
                workspace=workspace,
                project=project,
                spec_id=spec_id,
            )
            cards.extend(sdd_cards)
            evidence.extend(sdd_evidence)
            observer_cards, observer_evidence = _workspace_observer_cards(
                workspace=workspace,
                scope_id=str(scope["id"]),
            )
            cards.extend(observer_cards)
            evidence.extend(observer_evidence)
        pf_cards, pf_evidence, pf_continuity = self._project_factory_cards(
            draft_id=draft_id,
            job_id=job_id,
            workspace=workspace,
        )
        cards.extend(pf_cards)
        evidence.extend(pf_evidence)
        continuity.extend(pf_continuity)

        cards = _stable_unique_cards(cards)
        columns = _columns(cards)
        evidence_hash = _hash_payload(
            {
                "scope": scope,
                "cards": [
                    {
                        "id": card["id"],
                        "column": card["column"],
                        "status": card["status"],
                        "evidenceHash": card["evidenceHash"],
                    }
                    for card in cards
                ],
            }
        )
        snapshot_id = f"kanban-{evidence_hash[:16]}"
        delta = _delta(previous, cards=cards, evidence_hash=evidence_hash)
        board = {
            "snapshotId": snapshot_id,
            "evidenceHash": evidence_hash,
            "updatedAt": now,
            "columns": columns,
            "cards": cards,
            "counts": {column["id"]: column["count"] for column in columns},
            "delta": delta,
            "refresh": {
                "mode": "change-triggered",
                "forceRefresh": force_refresh,
                "debounceMs": 1500,
                "pollingFallbackSeconds": _POLL_INTERVAL_SECONDS,
                "lastRefreshedAt": now,
                "nextSuggestedRefreshAt": _iso_after(seconds=_POLL_INTERVAL_SECONDS),
                "watchedSources": [
                    "metadata.yaml",
                    "tasks.md",
                    "tree.json",
                    "plan.md",
                    "project_factory_state",
                    "codex_jsonl_tail",
                    "known_run_artifacts",
                ],
            },
        }
        curator = self._curator_update(
            storage_root=storage_root,
            scope=scope,
            board=board,
            evidence=evidence,
            delta=delta,
            now=now,
        )
        payload = {
            "kind": "codex.sddWorkbenchKanban",
            "version": 1,
            "scope": scope,
            "board": board,
            "latestUpdate": curator["latest"],
            "historySummary": curator["historySummary"],
            "curator": {
                "promptVersion": "workbench-kanban-curator/v1",
                "readOnly": True,
                "inputEnvelope": {
                    "scope": scope,
                    "snapshotId": snapshot_id,
                    "evidenceHash": evidence_hash,
                    "delta": delta,
                    "evidenceCount": len(evidence),
                    "previousUpdateId": curator["previousUpdateId"],
                },
                "rules": [
                    "Curator summarizes observed state only.",
                    "Curator does not change tasks, approve work, reject work, or trigger Generator/Reviewer.",
                ],
            },
            "evidence": evidence[:120],
            "continuity": continuity,
        }
        _write_json(storage_root / "board-cache.json", payload)
        return SddWorkbenchKanbanResult(payload=payload, storage_root=storage_root)

    def history(
        self,
        *,
        workspace: Path | None = None,
        scope_id: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        storage_root = self._storage_root_for_history(
            workspace=workspace,
            scope_id=scope_id,
        )
        items = _read_history(storage_root)[: max(1, min(limit, _HISTORY_LIMIT))]
        return {
            "kind": "codex.sddWorkbenchKanbanHistory",
            "version": 1,
            "scopeId": scope_id or _workspace_scope_id(workspace),
            "history": items,
            "count": len(items),
        }

    def history_item(
        self,
        *,
        update_id: str,
        workspace: Path | None = None,
        scope_id: str | None = None,
    ) -> dict[str, Any] | None:
        storage_root = self._storage_root_for_history(
            workspace=workspace,
            scope_id=scope_id,
        )
        for item in _read_history(storage_root):
            if item.get("id") == update_id:
                return {
                    "kind": "codex.sddWorkbenchKanbanHistoryItem",
                    "version": 1,
                    "update": item,
                }
        return None

    def _scope_payload(
        self,
        *,
        workspace: Path | None,
        project: SddProject | None,
        spec_id: str | None,
        draft_id: str | None,
        job_id: str | None,
    ) -> dict[str, Any]:
        normalized_spec = (spec_id or "").strip() or None
        normalized_draft = (draft_id or "").strip() or None
        normalized_job = (job_id or "").strip() or None
        if normalized_job:
            return {
                "id": f"project-factory:job:{normalized_job}",
                "type": "project_factory_job",
                "jobId": normalized_job,
                "draftId": normalized_draft,
                "workspacePath": str(workspace) if workspace is not None else None,
                "title": f"New Project job {normalized_job}",
            }
        if normalized_draft:
            return {
                "id": f"project-factory:draft:{normalized_draft}",
                "type": "project_factory_draft",
                "draftId": normalized_draft,
                "workspacePath": str(workspace) if workspace is not None else None,
                "title": f"New Project draft {normalized_draft}",
            }
        if normalized_spec and project is not None:
            spec_title = next(
                (spec.title for spec in project.specs if spec.id == normalized_spec),
                normalized_spec,
            )
            return {
                "id": f"workspace:{project.workspace_path}:spec:{normalized_spec}",
                "type": "workspace_spec",
                "workspacePath": project.workspace_path,
                "specId": normalized_spec,
                "title": spec_title,
            }
        return {
            "id": f"workspace:{workspace}" if workspace is not None else "workspace:none",
            "type": "workspace",
            "workspacePath": str(workspace) if workspace is not None else None,
            "title": project.workspace_name if project is not None else "Workbench",
        }

    def _storage_root(self, *, workspace: Path | None, scope: dict[str, Any]) -> Path:
        if workspace is not None:
            return workspace / ".codex" / "workbench-kanban" / _safe_scope_filename(
                str(scope["id"])
            )
        return (
            self._projects_root
            / ".codex"
            / "workbench-kanban"
            / _safe_scope_filename(str(scope["id"]))
        )

    def _storage_root_for_history(
        self,
        *,
        workspace: Path | None,
        scope_id: str | None,
    ) -> Path:
        resolved_scope = scope_id or _workspace_scope_id(workspace)
        if workspace is not None:
            return (
                workspace
                / ".codex"
                / "workbench-kanban"
                / _safe_scope_filename(resolved_scope)
            )
        return (
            self._projects_root
            / ".codex"
            / "workbench-kanban"
            / _safe_scope_filename(resolved_scope)
        )

    def _project_factory_cards(
        self,
        *,
        draft_id: str | None,
        job_id: str | None,
        workspace: Path | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        if self._project_factory_service is None:
            return [], [], []
        cards: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        continuity: list[dict[str, Any]] = []
        requested_draft = (draft_id or "").strip() or None
        requested_job = (job_id or "").strip() or None
        drafts = self._project_factory_service.list_drafts(limit=50)
        jobs = self._project_factory_service.list_jobs(limit=50)
        if requested_draft:
            drafts = tuple(item for item in drafts if item.get("draft_id") == requested_draft)
        if requested_job:
            jobs = tuple(item for item in jobs if item.get("job_id") == requested_job)
        for draft in drafts:
            card = _project_factory_draft_card(draft)
            cards.append(card)
            evidence.append(_card_evidence(card, "project_factory_draft", "state"))
        for job in jobs:
            card = _project_factory_job_card(job)
            cards.append(card)
            evidence.append(_card_evidence(card, "project_factory_job", "state"))
            target_path = str(job.get("target_path") or job.get("project_path") or "")
            if target_path and workspace is not None:
                try:
                    same_workspace = Path(target_path).expanduser().resolve() == workspace
                except OSError:
                    same_workspace = False
                if same_workspace:
                    continuity.append(
                        {
                            "fromScope": f"project-factory:job:{job.get('job_id')}",
                            "toScope": f"workspace:{workspace}",
                            "status": "mapped",
                            "marker": "generated_repository_exists",
                        }
                    )
            for phase_card in _project_factory_phase_cards(job):
                cards.append(phase_card)
                evidence.append(_card_evidence(phase_card, "project_factory_phase", "step_logs"))
        return cards, evidence, continuity

    def _curator_update(
        self,
        *,
        storage_root: Path,
        scope: dict[str, Any],
        board: dict[str, Any],
        evidence: list[dict[str, Any]],
        delta: dict[str, Any],
        now: str,
    ) -> dict[str, Any]:
        latest = _read_json(storage_root / "latest-update.json")
        previous_update_id = latest.get("id") if latest else None
        evidence_hash = str(board["evidenceHash"])
        history = _read_history(storage_root)
        if latest.get("evidenceHash") == evidence_hash:
            return {
                "latest": latest,
                "previousUpdateId": previous_update_id,
                "historySummary": _history_summary(history, latest, no_op=True),
            }
        update = _generate_curator_update(
            scope=scope,
            board=board,
            evidence=evidence,
            delta=delta,
            now=now,
        )
        history.insert(0, update)
        history = history[:_HISTORY_LIMIT]
        _write_json(storage_root / "latest-update.json", update)
        _write_json(storage_root / "history.json", history)
        return {
            "latest": update,
            "previousUpdateId": previous_update_id,
            "historySummary": _history_summary(history, update, no_op=False),
        }


def _project_cards(
    *,
    workspace: Path,
    project: SddProject,
    spec_id: str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected_specs = [
        spec for spec in project.specs if spec_id is None or spec.id == spec_id
    ]
    cards: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    for spec in selected_specs:
        parsed_tasks = _parse_tasks_markdown(workspace / spec.path / "tasks.md")
        tree_tasks = _tree_task_records(spec)
        merged = {record["taskKey"]: record for record in parsed_tasks}
        for record in tree_tasks:
            existing = merged.get(record["taskKey"])
            if existing is not None:
                record = {**record, "checked": existing.get("checked", record.get("checked")), "line": existing.get("line")}
            merged[record["taskKey"]] = record
        task_records = sorted(
            merged.values(),
            key=lambda item: (
                int(item.get("phaseNumber") or 999),
                int(item.get("taskNumber") or 999),
                str(item.get("taskKey")),
            ),
        )
        ready_phase = _first_incomplete_phase(task_records)
        for record in task_records:
            card = _spec_task_card(spec=spec, record=record, ready_phase=ready_phase)
            cards.append(card)
            evidence.append(_card_evidence(card, "sdd_task", card["sourcePath"]))
        for card in _plan_phase_cards(spec, task_records):
            cards.append(card)
            evidence.append(_card_evidence(card, "sdd_plan_phase", card["sourcePath"]))
        if spec.missing:
            card = _blocker_card(
                card_id=f"blocker:{spec.id}:missing-artifacts",
                title=f"{spec.id} has missing SDD artifacts",
                detail=", ".join(spec.missing),
                source_path=spec.path,
                scope_id=spec.id,
            )
            cards.append(card)
            evidence.append(_card_evidence(card, "sdd_missing_artifact", spec.path))
        if spec.traceability_status if hasattr(spec, "traceability_status") else False:
            pass
    return cards, evidence


def _tree_task_records(spec: SddSpec) -> list[dict[str, Any]]:
    if spec.tree is None:
        return []
    records: list[dict[str, Any]] = []
    for plan in spec.tree.plans:
        for task in plan.tasks:
            task_key = _task_key(task.title) or task.id
            records.append(
                {
                    "taskKey": task_key,
                    "title": _clean_task_title(task.title, task_key),
                    "status": task.status or "planned",
                    "checked": task.status == "completed",
                    "phaseId": plan.id,
                    "phaseTitle": plan.title,
                    "phaseNumber": plan.number,
                    "taskNumber": task.number,
                    "description": task.description,
                    "sourcePath": task.file.path if task.file else f"{spec.path}/tree.json",
                }
            )
    return records


def _parse_tasks_markdown(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    records: list[dict[str, Any]] = []
    phase_title = "Tasks"
    phase_number = 1
    seen_phase_titles: dict[str, int] = {}
    for line_number, line in enumerate(lines, start=1):
        if line.startswith("#"):
            phase_title = line.lstrip("#").strip() or "Tasks"
            phase_number = seen_phase_titles.setdefault(
                phase_title,
                len(seen_phase_titles) + 1,
            )
            continue
        match = _TASK_LINE_RE.match(line)
        if match is None:
            continue
        task_key = match.group("task")
        title = _clean_task_title(match.group("title"), task_key)
        checked = match.group("mark").lower() == "x"
        lowered = title.lower()
        status = "completed" if checked else "planned"
        if not checked and any(word in lowered for word in ("blocked", "bloqueado", "failed")):
            status = "blocked"
        elif not checked and any(word in lowered for word in ("review", "validation", "validacion", "validación")):
            status = "review"
        elif not checked and any(word in lowered for word in ("in progress", "en progreso", "running")):
            status = "in_progress"
        records.append(
            {
                "taskKey": task_key,
                "title": title,
                "status": status,
                "checked": checked,
                "phaseTitle": phase_title,
                "phaseNumber": phase_number,
                "taskNumber": len(records) + 1,
                "line": line_number,
                "sourcePath": path.parent.name + "/tasks.md",
            }
        )
    return records


def _spec_task_card(
    *,
    spec: SddSpec,
    record: dict[str, Any],
    ready_phase: int | None,
) -> dict[str, Any]:
    status = str(record.get("status") or "planned")
    phase_number = int(record.get("phaseNumber") or 999)
    task_number = int(record.get("taskNumber") or 999)
    column = _task_column(status=status, checked=bool(record.get("checked")), phase_number=phase_number, ready_phase=ready_phase)
    source_path = str(record.get("sourcePath") or f"{spec.path}/tasks.md")
    evidence = [
        {
            "sourceType": "sdd_task",
            "path": source_path,
            "line": record.get("line"),
            "confidence": "confirmed" if record.get("checked") else "observed",
            "confirmed": bool(record.get("checked")),
        }
    ]
    task_key = str(record["taskKey"])
    return _card(
        card_id=f"spec-task:{spec.id}:{task_key}",
        card_type="spec_task",
        title=f"{task_key} {record.get('title') or ''}".strip(),
        column=column,
        status=status,
        scope_id=spec.id,
        source_path=source_path,
        order=(phase_number * 1000) + task_number,
        confirmed=bool(record.get("checked")),
        inferred=False,
        badges=[str(record.get("phaseTitle") or "Phase")],
        evidence=evidence,
        detail=str(record.get("description") or ""),
    )


def _plan_phase_cards(spec: SddSpec, task_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_phase: dict[int, list[dict[str, Any]]] = {}
    for record in task_records:
        by_phase.setdefault(int(record.get("phaseNumber") or 999), []).append(record)
    cards: list[dict[str, Any]] = []
    for phase_number, records in sorted(by_phase.items()):
        total = len(records)
        done = sum(1 for record in records if record.get("checked"))
        blocked = any(str(record.get("status")) == "blocked" for record in records)
        active = any(str(record.get("status")) in {"in_progress", "review"} for record in records)
        if done == total and total:
            column = "done"
            status = "completed"
        elif blocked:
            column = "blocked"
            status = "blocked"
        elif active or done:
            column = "in_progress"
            status = "in_progress"
        else:
            column = "ready" if phase_number == _first_incomplete_phase(task_records) else "backlog"
            status = "planned"
        phase_title = str(records[0].get("phaseTitle") or f"Phase {phase_number}")
        cards.append(
            _card(
                card_id=f"plan-phase:{spec.id}:{phase_number}",
                card_type="plan_phase",
                title=f"{phase_title} ({done}/{total})",
                column=column,
                status=status,
                scope_id=spec.id,
                source_path=f"{spec.path}/plan.md",
                order=phase_number * 100,
                confirmed=False,
                inferred=False,
                badges=["phase", f"{done}/{total}"],
                evidence=[
                    {
                        "sourceType": "sdd_plan_phase",
                        "path": f"{spec.path}/tree.json",
                        "confidence": "observed",
                        "confirmed": False,
                    }
                ],
                detail=f"{done} of {total} tasks complete.",
            )
        )
    return cards


def _workspace_observer_cards(
    *,
    workspace: Path,
    scope_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cards: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    cards.extend(_bounded_jsonl_cards(workspace=workspace, scope_id=scope_id))
    cards.extend(_known_run_artifact_cards(workspace=workspace, scope_id=scope_id))
    cards.extend(_review_finding_cards(workspace=workspace, scope_id=scope_id))
    for card in cards:
        evidence.append(_card_evidence(card, str(card["type"]), str(card["sourcePath"])))
    return cards, evidence


def _bounded_jsonl_cards(*, workspace: Path, scope_id: str) -> list[dict[str, Any]]:
    candidates = sorted((workspace / ".codex").glob("**/*.jsonl"))[:5]
    cards: list[dict[str, Any]] = []
    for path in candidates:
        try:
            tail = _read_tail(path, limit=12000)
        except OSError:
            continue
        if not tail.strip():
            continue
        rel = _rel(path, workspace)
        title = "Codex activity observed"
        if "review" in tail.lower():
            title = "Reviewer activity observed"
        elif "generator" in tail.lower() or "implement" in tail.lower():
            title = "Generator activity observed"
        cards.append(
            _card(
                card_id=f"run-step:jsonl:{_safe_scope_filename(rel)}",
                card_type="run_step",
                title=title,
                column="in_progress",
                status="observed",
                scope_id=scope_id,
                source_path=rel,
                order=50000,
                confirmed=False,
                inferred=True,
                badges=["inferred", "jsonl-tail"],
                evidence=[
                    {
                        "sourceType": "codex_jsonl_tail",
                        "path": rel,
                        "confidence": "inferred",
                        "confirmed": False,
                    }
                ],
                detail="Bounded JSONL tail was observed without reading the full transcript.",
            )
        )
    return cards


def _known_run_artifact_cards(*, workspace: Path, scope_id: str) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for path in sorted((workspace / ".codex-bridge").glob("**/*status*.json"))[:20]:
        payload = _read_json(path)
        if not payload:
            continue
        status = str(payload.get("status") or payload.get("state") or "observed")
        lowered = status.lower()
        column = "blocked" if lowered in {"failed", "blocked", "error"} else "done" if lowered in {"passed", "ready", "completed"} else "in_progress"
        rel = _rel(path, workspace)
        cards.append(
            _card(
                card_id=f"run-step:artifact:{_safe_scope_filename(rel)}",
                card_type="run_step",
                title=f"Run artifact {status}",
                column=column,
                status=status,
                scope_id=scope_id,
                source_path=rel,
                order=51000,
                confirmed=False,
                inferred=True,
                badges=["artifact", status],
                evidence=[
                    {
                        "sourceType": "known_run_artifact",
                        "path": rel,
                        "confidence": "observed",
                        "confirmed": False,
                    }
                ],
                detail=str(payload.get("message") or payload.get("error") or ""),
            )
        )
    preview_runtime = workspace / "release" / "preview-runtime.json"
    if preview_runtime.is_file():
        payload = _read_json(preview_runtime)
        blocked = payload.get("productionReady") is True or payload.get("mockOrDemo") is True
        cards.append(
            _card(
                card_id="run-step:release:preview-runtime",
                card_type="run_step",
                title="Initial Preview runtime contract",
                column="blocked" if blocked else "review",
                status="blocked" if blocked else "validation",
                scope_id=scope_id,
                source_path="release/preview-runtime.json",
                order=52000,
                confirmed=False,
                inferred=True,
                badges=["release", "preview"],
                evidence=[
                    {
                        "sourceType": "release_contract",
                        "path": "release/preview-runtime.json",
                        "confidence": "observed",
                        "confirmed": False,
                    }
                ],
                detail="Preview release contract is present.",
            )
        )
    return cards


def _review_finding_cards(*, workspace: Path, scope_id: str) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    candidates = sorted(workspace.glob("**/review*.md"))[:20] + sorted(
        workspace.glob("**/review*.json")
    )[:20]
    for path in candidates:
        if ".git" in path.parts:
            continue
        try:
            text = _read_tail(path, limit=24000)
        except OSError:
            continue
        lowered = text.lower()
        if not any(marker in lowered for marker in ("finding", "issue", "blocked", "requested changes", "unresolved")):
            continue
        rel = _rel(path, workspace)
        unresolved = "unresolved" in lowered or "requested changes" in lowered or "- [ ]" in lowered
        cards.append(
            _card(
                card_id=f"review-finding:{_safe_scope_filename(rel)}",
                card_type="review_finding",
                title="Reviewer finding observed",
                column="review" if unresolved else "done",
                status="unresolved" if unresolved else "observed",
                scope_id=scope_id,
                source_path=rel,
                order=53000,
                confirmed=False,
                inferred=True,
                badges=["review", "inferred"],
                evidence=[
                    {
                        "sourceType": "review_artifact",
                        "path": rel,
                        "confidence": "inferred",
                        "confirmed": False,
                    }
                ],
                detail="Reviewer finding text was safely detectable from an existing artifact.",
            )
        )
    return cards


def _project_factory_draft_card(draft: dict[str, Any]) -> dict[str, Any]:
    ok = draft.get("ok") is True
    status = str(draft.get("status") or "draft")
    column = "ready" if ok else "blocked"
    return _card(
        card_id=f"project-factory:draft:{draft.get('draft_id')}",
        card_type="run_step",
        title=f"New Project draft: {draft.get('name') or draft.get('draft_id')}",
        column=column,
        status=status,
        scope_id=str(draft.get("draft_id") or "project-factory"),
        source_path="project_factory_state/drafts",
        order=60000,
        confirmed=False,
        inferred=True,
        badges=["draft", str(draft.get("first_release_mode") or "preview")],
        evidence=[
            {
                "sourceType": "project_factory_draft",
                "path": "project_factory_state/drafts",
                "confidence": "observed",
                "confirmed": False,
            }
        ],
        detail=str(draft.get("error") or draft.get("primary_goal") or ""),
    )


def _project_factory_job_card(job: dict[str, Any]) -> dict[str, Any]:
    status = str(job.get("status") or "queued")
    if status in {"blocked", "failed", "interrupted"}:
        column = "blocked"
    elif status == "ready":
        column = "done"
    elif status in {"running", "queued"}:
        column = "in_progress"
    else:
        column = "ready"
    return _card(
        card_id=f"project-factory:job:{job.get('job_id')}",
        card_type="run_step",
        title=f"New Project job: {job.get('name') or job.get('job_id')}",
        column=column,
        status=status,
        scope_id=str(job.get("job_id") or "project-factory"),
        source_path="project_factory_state/jobs",
        order=61000,
        confirmed=False,
        inferred=True,
        badges=["job", str(job.get("current_phase") or "queued")],
        evidence=[
            {
                "sourceType": "project_factory_job",
                "path": "project_factory_state/jobs",
                "confidence": "observed",
                "confirmed": False,
            }
        ],
        detail=str(job.get("error") or job.get("message") or ""),
    )


def _project_factory_phase_cards(job: dict[str, Any]) -> list[dict[str, Any]]:
    preview = job.get("initial_preview_release")
    if not isinstance(preview, dict):
        return []
    phases = preview.get("phaseStatuses")
    if not isinstance(phases, dict):
        return []
    cards: list[dict[str, Any]] = []
    for index, (phase, raw_status) in enumerate(sorted(phases.items()), start=1):
        if not isinstance(raw_status, dict):
            continue
        status = str(raw_status.get("status") or "pending")
        column = "done" if status == "completed" else "blocked" if status in {"blocked", "failed"} else "in_progress" if status in {"running", "active"} else "ready"
        cards.append(
            _card(
                card_id=f"project-factory:job:{job.get('job_id')}:phase:{phase}",
                card_type="run_step",
                title=f"Preview release phase: {phase.replace('_', ' ')}",
                column=column,
                status=status,
                scope_id=str(job.get("job_id") or "project-factory"),
                source_path="project_factory_state/jobs",
                order=62000 + index,
                confirmed=False,
                inferred=True,
                badges=["preview-release", status],
                evidence=[
                    {
                        "sourceType": "project_factory_phase",
                        "path": "project_factory_state/jobs",
                        "confidence": "observed",
                        "confirmed": False,
                    }
                ],
                detail=str(raw_status.get("message") or ""),
                manual_commands=raw_status.get("command") if isinstance(raw_status.get("command"), list) else [],
            )
        )
    return cards


def _blocker_card(
    *,
    card_id: str,
    title: str,
    detail: str,
    source_path: str,
    scope_id: str,
) -> dict[str, Any]:
    return _card(
        card_id=card_id,
        card_type="blocker",
        title=title,
        column="blocked",
        status="blocked",
        scope_id=scope_id,
        source_path=source_path,
        order=90000,
        confirmed=False,
        inferred=False,
        badges=["blocker"],
        evidence=[
            {
                "sourceType": "sdd_artifact",
                "path": source_path,
                "confidence": "observed",
                "confirmed": False,
            }
        ],
        detail=detail,
    )


def _card(
    *,
    card_id: str,
    card_type: str,
    title: str,
    column: str,
    status: str,
    scope_id: str,
    source_path: str,
    order: int,
    confirmed: bool,
    inferred: bool,
    badges: list[str],
    evidence: list[dict[str, Any]],
    detail: str = "",
    manual_commands: list[Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "id": card_id,
        "type": card_type,
        "title": title,
        "column": column,
        "status": status,
        "scopeId": scope_id,
        "sourcePath": source_path,
        "order": order,
        "confirmed": confirmed,
        "inferred": inferred,
        "confidence": "confirmed" if confirmed else "inferred" if inferred else "observed",
        "badges": badges,
        "detail": detail,
        "evidence": evidence,
        "manualCommands": manual_commands or [],
    }
    payload["evidenceHash"] = _hash_payload(
        {
            "id": card_id,
            "column": column,
            "status": status,
            "evidence": evidence,
            "detail": detail,
        }
    )
    return payload


def _task_column(
    *,
    status: str,
    checked: bool,
    phase_number: int,
    ready_phase: int | None,
) -> str:
    normalized = status.lower().replace("-", "_")
    if checked or normalized in {"complete", "completed", "done"}:
        return "done"
    if normalized in {"blocked", "failed", "error"}:
        return "blocked"
    if normalized in {"review", "in_review", "validation", "review_required"}:
        return "review"
    if normalized in {"active", "running", "in_progress"}:
        return "in_progress"
    if ready_phase is None or phase_number == ready_phase:
        return "ready"
    return "backlog"


def _first_incomplete_phase(records: list[dict[str, Any]]) -> int | None:
    for phase in sorted({int(record.get("phaseNumber") or 999) for record in records}):
        phase_records = [record for record in records if int(record.get("phaseNumber") or 999) == phase]
        if any(not record.get("checked") for record in phase_records):
            return phase
    return None


def _columns(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    columns: list[dict[str, Any]] = []
    for column_id in KANBAN_COLUMN_ORDER:
        column_cards = [
            card["id"]
            for card in sorted(
                (card for card in cards if card["column"] == column_id),
                key=lambda item: (int(item["order"]), str(item["id"])),
            )
        ]
        columns.append(
            {
                "id": column_id,
                "label": KANBAN_COLUMN_LABELS[column_id],
                "cardIds": column_cards,
                "count": len(column_cards),
            }
        )
    return columns


def _delta(
    previous: dict[str, Any],
    *,
    cards: list[dict[str, Any]],
    evidence_hash: str,
) -> dict[str, Any]:
    previous_board = previous.get("board") if isinstance(previous, dict) else None
    previous_cards = previous_board.get("cards") if isinstance(previous_board, dict) else None
    previous_by_id = {
        str(card.get("id")): card
        for card in previous_cards
        if isinstance(card, dict) and card.get("id")
    } if isinstance(previous_cards, list) else {}
    current_by_id = {str(card["id"]): card for card in cards}
    added = sorted(set(current_by_id) - set(previous_by_id))
    removed = sorted(set(previous_by_id) - set(current_by_id))
    moved = []
    changed = []
    for card_id, card in current_by_id.items():
        previous_card = previous_by_id.get(card_id)
        if previous_card is None:
            continue
        if previous_card.get("column") != card.get("column"):
            moved.append(
                {
                    "cardId": card_id,
                    "from": previous_card.get("column"),
                    "to": card.get("column"),
                }
            )
        elif previous_card.get("evidenceHash") != card.get("evidenceHash"):
            changed.append(card_id)
    previous_hash = (
        previous_board.get("evidenceHash")
        if isinstance(previous_board, dict)
        else None
    )
    return {
        "changed": previous_hash != evidence_hash,
        "previousEvidenceHash": previous_hash,
        "addedCardIds": added,
        "removedCardIds": removed,
        "movedCards": moved,
        "changedCardIds": sorted(changed),
        "summary": {
            "added": len(added),
            "removed": len(removed),
            "moved": len(moved),
            "changed": len(changed),
        },
    }


def _generate_curator_update(
    *,
    scope: dict[str, Any],
    board: dict[str, Any],
    evidence: list[dict[str, Any]],
    delta: dict[str, Any],
    now: str,
) -> dict[str, Any]:
    counts = board["counts"]
    blocker_count = int(counts.get("blocked") or 0)
    in_progress_count = int(counts.get("in_progress") or 0)
    review_count = int(counts.get("review") or 0)
    done_count = int(counts.get("done") or 0)
    title = "Workbench Kanban updated"
    if blocker_count:
        title = f"{blocker_count} blocker(s) visible"
    elif in_progress_count:
        title = f"{in_progress_count} item(s) in progress"
    elif review_count:
        title = f"{review_count} item(s) waiting on review"
    summary = (
        f"{scope.get('title')} has {done_count} done, {in_progress_count} in progress, "
        f"{review_count} in review, and {blocker_count} blocked cards."
    )
    changed_cards = [
        *delta.get("addedCardIds", []),
        *[item.get("cardId") for item in delta.get("movedCards", []) if isinstance(item, dict)],
        *delta.get("changedCardIds", []),
    ]
    return {
        "id": f"curator-{_hash_payload({'scope': scope, 'hash': board['evidenceHash']})[:16]}",
        "timestamp": now,
        "scope": scope,
        "snapshotId": board["snapshotId"],
        "evidenceHash": board["evidenceHash"],
        "title": title,
        "summary": summary,
        "changedCards": sorted({str(item) for item in changed_cards if item}),
        "changedCounts": delta.get("summary", {}),
        "importantEvidence": evidence[:10],
        "blockers": [
            card["title"]
            for card in board["cards"]
            if card.get("column") == "blocked"
        ][:8],
        "risks": [
            "Inferred cards are observational only and do not confirm task completion."
        ],
        "nextWatch": _next_watch(counts),
    }


def _next_watch(counts: dict[str, Any]) -> str:
    if int(counts.get("blocked") or 0):
        return "Watch blocker cards and validation evidence before reporting readiness."
    if int(counts.get("review") or 0):
        return "Watch Reviewer or validation outcomes."
    if int(counts.get("in_progress") or 0):
        return "Watch active run steps and task status updates."
    return "Watch for new SDD task movement or Project Factory jobs."


def _history_summary(
    history: list[dict[str, Any]],
    latest: dict[str, Any],
    *,
    no_op: bool,
) -> dict[str, Any]:
    return {
        "count": len(history),
        "latestUpdateId": latest.get("id") if latest else None,
        "latestTimestamp": latest.get("timestamp") if latest else None,
        "noOp": no_op,
        "retentionLimit": _HISTORY_LIMIT,
    }


def _read_history(storage_root: Path) -> list[dict[str, Any]]:
    payload = _read_json(storage_root / "history.json")
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _stable_unique_cards(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for card in cards:
        by_id[str(card["id"])] = card
    return sorted(by_id.values(), key=lambda item: (str(item["column"]), int(item["order"]), str(item["id"])))


def _card_evidence(card: dict[str, Any], source_type: str, path: str) -> dict[str, Any]:
    return {
        "cardId": card["id"],
        "sourceType": source_type,
        "path": path,
        "confidence": card["confidence"],
        "confirmed": card["confirmed"],
        "evidenceHash": card["evidenceHash"],
    }


def _task_key(value: str) -> str | None:
    match = _TASK_ID_RE.search(value)
    return match.group(1) if match else None


def _clean_task_title(value: str, task_key: str | None) -> str:
    cleaned = value.strip(" :-.\t")
    if task_key and cleaned.startswith(task_key):
        cleaned = cleaned[len(task_key) :].strip(" :-.\t")
    return cleaned or task_key or "Task"


def _workspace_scope_id(workspace: Path | None) -> str:
    return f"workspace:{workspace}" if workspace is not None else "workspace:none"


def _safe_scope_filename(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")
    return safe[:120] or "scope"


def _rel(path: Path, workspace: Path) -> str:
    try:
        return path.relative_to(workspace).as_posix()
    except ValueError:
        return str(path)


def _read_tail(path: Path, *, limit: int) -> str:
    with path.open("rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        handle.seek(max(0, size - limit), 0)
        return handle.read().decode("utf-8", errors="replace")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _hash_payload(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _iso_after(*, seconds: int) -> str:
    return (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat().replace(
        "+00:00",
        "Z",
    )

