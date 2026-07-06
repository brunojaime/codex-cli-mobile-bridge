from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.app.application.services.sdd_standard_service import (
    SddStandardError,
    parse_simple_yaml,
)


@dataclass(frozen=True, slots=True)
class SddMetadataTaskSummary:
    total: int
    completed: int
    pending: int

    def to_payload(self) -> dict[str, int]:
        return {
            "total": self.total,
            "completed": self.completed,
            "pending": self.pending,
        }


@dataclass(frozen=True, slots=True)
class SddMetadataDiagramSummary:
    total: int
    diagrams: tuple[dict[str, str], ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "total": self.total,
            "diagrams": [dict(item) for item in self.diagrams],
        }


@dataclass(frozen=True, slots=True)
class SddMetadataRefreshResult:
    status: str
    mode: str
    workspace_path: str
    spec_id: str
    metadata_path: str
    title: str
    description: str
    proposed_title: str
    proposed_description: str
    changed_fields: tuple[str, ...]
    skipped_fields: tuple[str, ...]
    pinned_fields: tuple[str, ...]
    stale_paths: tuple[str, ...]
    source_digests: dict[str, str]
    task_summary: SddMetadataTaskSummary
    diagram_summary: SddMetadataDiagramSummary
    would_write: bool
    written: bool
    blocked: tuple[str, ...]
    next_actions: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "kind": "codex.sddMetadataRefresh",
            "version": 1,
            "status": self.status,
            "mode": self.mode,
            "workspace_path": self.workspace_path,
            "spec_id": self.spec_id,
            "metadata_path": self.metadata_path,
            "title": self.title,
            "description": self.description,
            "proposed_title": self.proposed_title,
            "proposed_description": self.proposed_description,
            "changed_fields": list(self.changed_fields),
            "skipped_fields": list(self.skipped_fields),
            "pinned_fields": list(self.pinned_fields),
            "stale_paths": list(self.stale_paths),
            "source_digests": dict(self.source_digests),
            "task_summary": self.task_summary.to_payload(),
            "diagram_summary": self.diagram_summary.to_payload(),
            "would_write": self.would_write,
            "written": self.written,
            "blocked": list(self.blocked),
            "next_actions": list(self.next_actions),
        }


class SddMetadataRefreshService:
    def __init__(
        self,
        *,
        projects_root: str | Path,
        workspace_aliases: dict[str, str] | None = None,
    ) -> None:
        self._projects_root = Path(projects_root).expanduser().resolve()
        self._workspace_aliases = {
            key: Path(value).expanduser().resolve()
            for key, value in (workspace_aliases or {}).items()
            if key.strip() and str(value).strip()
        }

    def preview_spec_metadata(
        self,
        workspace_path: str | Path,
        spec_id: str,
    ) -> SddMetadataRefreshResult:
        return self._refresh(workspace_path, spec_id, apply=False)

    def refresh_spec_metadata(
        self,
        workspace_path: str | Path,
        spec_id: str,
    ) -> SddMetadataRefreshResult:
        return self._refresh(workspace_path, spec_id, apply=True)

    def _refresh(
        self,
        workspace_path: str | Path,
        spec_id: str,
        *,
        apply: bool,
    ) -> SddMetadataRefreshResult:
        workspace = self._validate_workspace(workspace_path)
        clean_spec_id = _validate_spec_id(spec_id)
        spec_root = workspace / "specs" / clean_spec_id
        metadata_path = spec_root / "metadata.yaml"
        relative_metadata_path = metadata_path.relative_to(workspace).as_posix()
        if not spec_root.is_dir():
            return _blocked_result(
                workspace=workspace,
                spec_id=clean_spec_id,
                metadata_path=relative_metadata_path,
                mode="apply" if apply else "preview",
                blocked=(f"spec root not found: specs/{clean_spec_id}",),
            )

        existing = _read_metadata(metadata_path)
        sources = _collect_sources(workspace, spec_root)
        source_digests = {
            path: hashlib.sha256(file_path.read_bytes()).hexdigest()
            for path, file_path in sources.items()
        }
        stale_paths = _stale_paths(existing, source_digests)
        proposed_title = _proposed_title(spec_root, clean_spec_id)
        proposed_description = _proposed_description(spec_root, proposed_title)
        pinned_fields = _pinned_fields(existing)
        title = (
            str(existing.get("title") or proposed_title)
            if "title" in pinned_fields
            else proposed_title
        )
        description = (
            str(existing.get("description") or proposed_description)
            if "description" in pinned_fields
            else proposed_description
        )
        task_summary = _task_summary(spec_root / "tasks.md")
        diagram_summary = _diagram_summary(spec_root)
        desired = _desired_metadata(
            spec_id=clean_spec_id,
            existing=existing,
            title=title,
            description=description,
            proposed_title=proposed_title,
            proposed_description=proposed_description,
            source_digests=source_digests,
            task_summary=task_summary,
            diagram_summary=diagram_summary,
            pinned_fields=pinned_fields,
        )
        current_text = (
            metadata_path.read_text(encoding="utf-8") if metadata_path.is_file() else ""
        )
        desired_text = _metadata_yaml(desired)
        changed_fields = _changed_fields(existing, desired)
        skipped_fields = tuple(
            field
            for field in ("title", "description")
            if field in pinned_fields
            and str(existing.get(field) or "")
            != str(
                {
                    "title": proposed_title,
                    "description": proposed_description,
                }[field]
            )
        )
        would_write = current_text != desired_text
        if apply and would_write:
            _write_atomic(metadata_path, desired_text)

        mode = "apply" if apply else "preview"
        status = "updated" if apply and would_write else "unchanged"
        if not apply:
            status = "preview"
        return SddMetadataRefreshResult(
            status=status,
            mode=mode,
            workspace_path=str(workspace),
            spec_id=clean_spec_id,
            metadata_path=relative_metadata_path,
            title=title,
            description=description,
            proposed_title=proposed_title,
            proposed_description=proposed_description,
            changed_fields=changed_fields,
            skipped_fields=skipped_fields,
            pinned_fields=pinned_fields,
            stale_paths=stale_paths,
            source_digests=source_digests,
            task_summary=task_summary,
            diagram_summary=diagram_summary,
            would_write=would_write,
            written=apply and would_write,
            blocked=(),
            next_actions=()
            if apply
            else ("Run metadata refresh apply after reviewing the preview.",),
        )

    def _validate_workspace(self, workspace_path: str | Path) -> Path:
        raw = str(workspace_path).strip()
        if not raw:
            raise ValueError("workspace_path is required.")
        alias_path = self._workspace_aliases.get(raw)
        candidate = alias_path if alias_path is not None else Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = self._projects_root / candidate
        resolved = candidate.resolve()
        if not _is_relative_to(resolved, self._projects_root) and not any(
            resolved == alias for alias in self._workspace_aliases.values()
        ):
            raise ValueError(
                "workspace_path must resolve under PROJECTS_ROOT or a known alias."
            )
        if not resolved.is_dir():
            raise ValueError("workspace_path must point to a directory.")
        return resolved


def _blocked_result(
    *,
    workspace: Path,
    spec_id: str,
    metadata_path: str,
    mode: str,
    blocked: tuple[str, ...],
) -> SddMetadataRefreshResult:
    return SddMetadataRefreshResult(
        status="blocked",
        mode=mode,
        workspace_path=str(workspace),
        spec_id=spec_id,
        metadata_path=metadata_path,
        title="",
        description="",
        proposed_title="",
        proposed_description="",
        changed_fields=(),
        skipped_fields=(),
        pinned_fields=(),
        stale_paths=(),
        source_digests={},
        task_summary=SddMetadataTaskSummary(total=0, completed=0, pending=0),
        diagram_summary=SddMetadataDiagramSummary(total=0, diagrams=()),
        would_write=False,
        written=False,
        blocked=blocked,
        next_actions=("Fix metadata refresh blockers before applying.",),
    )


def _validate_spec_id(spec_id: str) -> str:
    clean = spec_id.strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,159}", clean):
        raise ValueError("spec_id must be a safe relative spec directory name.")
    if clean in {".", ".."}:
        raise ValueError("spec_id must be a safe relative spec directory name.")
    return clean


def _read_metadata(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        parsed = parse_simple_yaml(path.read_text(encoding="utf-8"))
    except SddStandardError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _collect_sources(workspace: Path, spec_root: Path) -> dict[str, Path]:
    paths: list[Path] = []
    for relative in (
        "spec.md",
        "plan.md",
        "tasks.md",
        "traceability.yaml",
        "intake/original-request.md",
        "intake/transcript.md",
        "intake/visual-summary.md",
    ):
        path = spec_root / relative
        if path.is_file():
            paths.append(path)
    for path in sorted((spec_root / "diagrams").glob("*")):
        if path.is_file() and path.suffix.lower() in {".mmd", ".yaml", ".yml"}:
            paths.append(path)
    return {
        path.relative_to(spec_root).as_posix(): path
        for path in sorted(set(paths), key=lambda item: item.as_posix())
        if _is_relative_to(path.resolve(), workspace)
    }


def _stale_paths(
    existing: dict[str, Any],
    source_digests: dict[str, str],
) -> tuple[str, ...]:
    raw = existing.get("source_digests")
    if not isinstance(raw, dict):
        return ()
    stale = [
        path
        for path, digest in sorted(raw.items(), key=lambda item: str(item[0]))
        if source_digests.get(str(path)) != str(digest)
    ]
    return tuple(stale)


def _pinned_fields(existing: dict[str, Any]) -> tuple[str, ...]:
    generated = existing.get("generated")
    if not isinstance(generated, dict):
        return ()
    pinned: list[str] = []
    if _as_bool(generated.get("user_pinned_title")):
        pinned.append("title")
    if _as_bool(generated.get("user_pinned_description")):
        pinned.append("description")
    return tuple(pinned)


def _proposed_title(spec_root: Path, spec_id: str) -> str:
    heading = _first_heading(spec_root / "spec.md")
    return heading or _humanize(spec_id)


def _proposed_description(spec_root: Path, title: str) -> str:
    description = _first_body_paragraph(spec_root / "spec.md")
    if description:
        return description[:240]
    return f"Spec for {title}."


def _task_summary(path: Path) -> SddMetadataTaskSummary:
    if not path.is_file():
        return SddMetadataTaskSummary(total=0, completed=0, pending=0)
    total = 0
    completed = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip().lower()
        if stripped.startswith(("- [ ]", "* [ ]")):
            total += 1
        elif stripped.startswith(("- [x]", "* [x]")):
            total += 1
            completed += 1
    return SddMetadataTaskSummary(
        total=total,
        completed=completed,
        pending=max(total - completed, 0),
    )


def _diagram_summary(spec_root: Path) -> SddMetadataDiagramSummary:
    diagrams: list[dict[str, str]] = []
    for path in sorted((spec_root / "diagrams").glob("*.mmd")):
        if not path.is_file():
            continue
        relative = path.relative_to(spec_root).as_posix()
        sidecar = path.with_suffix(".yaml")
        metadata = _read_metadata(sidecar)
        diagrams.append(
            {
                "path": relative,
                "diagram_type": str(
                    metadata.get("diagram_type") or _diagram_type(path)
                ),
                "metadata_path": sidecar.relative_to(spec_root).as_posix()
                if sidecar.is_file()
                else "",
            }
        )
    return SddMetadataDiagramSummary(total=len(diagrams), diagrams=tuple(diagrams))


def _desired_metadata(
    *,
    spec_id: str,
    existing: dict[str, Any],
    title: str,
    description: str,
    proposed_title: str,
    proposed_description: str,
    source_digests: dict[str, str],
    task_summary: SddMetadataTaskSummary,
    diagram_summary: SddMetadataDiagramSummary,
    pinned_fields: tuple[str, ...],
) -> dict[str, Any]:
    generated = existing.get("generated")
    if not isinstance(generated, dict):
        generated = {}
    return {
        "id": str(existing.get("id") or spec_id),
        "slug": str(existing.get("slug") or spec_id),
        "title": title,
        "description": description,
        "status": str(existing.get("status") or "draft"),
        "created_at": str(existing.get("created_at") or ""),
        "updated_at": str(existing.get("updated_at") or ""),
        "last_run_state": str(existing.get("last_run_state") or "metadata-refreshed"),
        "generated": {
            "title": (
                "title" not in pinned_fields
                and (
                    _as_bool(generated.get("title"))
                    or not str(existing.get("title") or "").strip()
                )
            ),
            "description": (
                "description" not in pinned_fields
                and (
                    _as_bool(generated.get("description"))
                    or not str(existing.get("description") or "").strip()
                )
            ),
            "user_pinned_title": "title" in pinned_fields,
            "user_pinned_description": "description" in pinned_fields,
        },
        "tasks": task_summary.to_payload(),
        "diagrams": {
            "total": diagram_summary.total,
            "items": {
                _metadata_key(item["path"]): item for item in diagram_summary.diagrams
            },
        },
        "source_digests": source_digests,
    }


def _changed_fields(
    existing: dict[str, Any], desired: dict[str, Any]
) -> tuple[str, ...]:
    fields: list[str] = []
    for key in (
        "title",
        "description",
        "status",
        "last_run_state",
        "generated",
        "tasks",
        "diagrams",
        "source_digests",
    ):
        if existing.get(key) != desired.get(key):
            fields.append(key)
    return tuple(fields)


def _metadata_yaml(metadata: dict[str, Any]) -> str:
    lines = [
        f"id: {metadata['id']}",
        f"slug: {metadata['slug']}",
        f"title: {metadata['title']}",
        f"description: {metadata['description']}",
        f"status: {metadata['status']}",
    ]
    if metadata["created_at"]:
        lines.append(f"created_at: {metadata['created_at']}")
    if metadata["updated_at"]:
        lines.append(f"updated_at: {metadata['updated_at']}")
    lines.append(f"last_run_state: {metadata['last_run_state']}")
    lines.extend(
        [
            "generated:",
            f"  title: {_bool_text(metadata['generated']['title'])}",
            f"  description: {_bool_text(metadata['generated']['description'])}",
            (
                "  user_pinned_title: "
                f"{_bool_text(metadata['generated']['user_pinned_title'])}"
            ),
            (
                "  user_pinned_description: "
                f"{_bool_text(metadata['generated']['user_pinned_description'])}"
            ),
            "tasks:",
            f"  total: {metadata['tasks']['total']}",
            f"  completed: {metadata['tasks']['completed']}",
            f"  pending: {metadata['tasks']['pending']}",
            "diagrams:",
            f"  total: {metadata['diagrams']['total']}",
        ]
    )
    diagram_items = metadata["diagrams"]["items"]
    if diagram_items:
        lines.append("  items:")
        for item_id, item in sorted(diagram_items.items()):
            lines.extend(
                [
                    f"    {item_id}:",
                    f"      path: {item['path']}",
                    f"      diagram_type: {item['diagram_type']}",
                    f"      metadata_path: {item['metadata_path']}",
                ]
            )
    else:
        lines.append("  items: {}")
    lines.append("source_digests:")
    for path, digest in sorted(metadata["source_digests"].items()):
        lines.append(f"  {path}: {digest}")
    return "\n".join(lines) + "\n"


def _first_heading(path: Path) -> str | None:
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or None
    return None


def _first_body_paragraph(path: Path) -> str:
    if not path.is_file():
        return ""
    in_frontmatter = False
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped == "---":
            in_frontmatter = not in_frontmatter
            continue
        if in_frontmatter or not stripped or stripped.startswith("#"):
            continue
        if ":" in stripped and len(stripped.split(":", 1)[0].split()) <= 3:
            continue
        return " ".join(stripped.split())
    return ""


def _diagram_type(path: Path) -> str:
    first_line = ""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip():
            first_line = line.strip().lower()
            break
    if first_line.startswith("sequencediagram"):
        return "sequence"
    if first_line.startswith("classdiagram"):
        return "domain-impact"
    if first_line.startswith("erdiagram"):
        return "data-impact"
    if first_line.startswith(("flowchart", "graph")):
        return "component-impact"
    return "unknown"


def _humanize(value: str) -> str:
    return " ".join(part.capitalize() for part in re.split(r"[-_.]+", value) if part)


def _metadata_key(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-") or "diagram"


def _write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        temp_path.write_text(content, encoding="utf-8")
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1"}
    return False


def _bool_text(value: object) -> str:
    return "true" if bool(value) else "false"


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
