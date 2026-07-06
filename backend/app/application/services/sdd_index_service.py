from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.app.application.services.sdd_standard_service import (
    SddStandard,
    SddStandardError,
    parse_simple_yaml,
)


INDEX_FILENAMES = (
    "spec-index.yaml",
    "diagram-index.yaml",
    "module-index.yaml",
    "context-index.yaml",
)
SPEC_PREFIX_BYTES = 8192


@dataclass(frozen=True, slots=True)
class SddIndexStatus:
    state: str
    mode: str
    index_root: Path
    missing: tuple[str, ...] = ()
    stale: tuple[str, ...] = ()
    generated: tuple[str, ...] = ()
    failed: tuple[str, ...] = ()
    detail: str = ""


class SddIndexService:
    def ensure_indexes(
        self,
        workspace: Path,
        *,
        standard: SddStandard,
        auto_regenerate: bool,
        allow_degraded: bool = True,
    ) -> SddIndexStatus:
        workspace = workspace.expanduser().resolve()
        index_root = workspace / ".sdd"
        expected = _expected_index_paths(index_root)
        current_fingerprint = _workspace_fingerprint(workspace, standard)
        missing = tuple(
            filename for filename, path in expected.items() if not path.is_file()
        )
        stale = tuple(
            filename
            for filename, path in expected.items()
            if path.is_file() and _index_fingerprint(path) != current_fingerprint
        )
        if not missing and not stale:
            return SddIndexStatus(
                state="fresh",
                mode="normal",
                index_root=index_root,
                detail="All SDD indexes are fresh.",
            )
        if not auto_regenerate:
            state = "missing" if missing else "stale"
            blocked = missing or stale
            return SddIndexStatus(
                state=state,
                mode="hard_failure",
                index_root=index_root,
                missing=missing,
                stale=stale,
                failed=blocked,
                detail=(
                    "SDD indexes are not fresh and auto-regeneration is disabled; "
                    "context routing must not read all specs as a fallback."
                ),
            )
        try:
            payloads = _build_index_payloads(
                workspace,
                standard,
                fingerprint=current_fingerprint,
            )
            index_root.mkdir(parents=True, exist_ok=True)
            for filename, payload in payloads.items():
                (index_root / filename).write_text(
                    _dump_yaml(payload), encoding="utf-8"
                )
        except OSError as exc:
            return SddIndexStatus(
                state="failed",
                mode="degraded" if allow_degraded else "hard_failure",
                index_root=index_root,
                missing=missing,
                stale=stale,
                failed=tuple(INDEX_FILENAMES),
                detail=(
                    f"Index regeneration failed: {exc}; "
                    "degraded mode forbids all-spec fallback."
                ),
            )
        return SddIndexStatus(
            state="regenerated",
            mode="normal",
            index_root=index_root,
            missing=missing,
            stale=stale,
            generated=INDEX_FILENAMES,
            detail="SDD indexes regenerated deterministically.",
        )


def _expected_index_paths(index_root: Path) -> dict[str, Path]:
    return {filename: index_root / filename for filename in INDEX_FILENAMES}


def _build_index_payloads(
    workspace: Path,
    standard: SddStandard,
    *,
    fingerprint: str,
) -> dict[str, dict[str, Any]]:
    generated_at_epoch = int(time.time())
    manifest = _read_manifest(workspace)
    spec_entries = _spec_entries(workspace)
    diagram_entries = _diagram_entries(workspace)
    module_entries = _module_entries(manifest)
    common = {
        "kind": "codex.sdd.index",
        "standard_id": standard.id,
        "standard_version": standard.version,
        "fingerprint": fingerprint,
        "generated_at_epoch": generated_at_epoch,
        "read_policy": "prefix_only_no_full_spec_body",
    }
    return {
        "spec-index.yaml": {
            **common,
            "index_type": "spec",
            "specs": spec_entries,
        },
        "diagram-index.yaml": {
            **common,
            "index_type": "diagram",
            "diagrams": diagram_entries,
        },
        "module-index.yaml": {
            **common,
            "index_type": "module",
            "modules": module_entries,
        },
        "context-index.yaml": {
            **common,
            "index_type": "context",
            "candidate_limits": _candidate_limits(manifest),
            "indexes": {filename: f".sdd/{filename}" for filename in INDEX_FILENAMES},
            "index_status": "regenerated",
        },
    }


def _workspace_fingerprint(workspace: Path, standard: SddStandard) -> str:
    sources = []
    for path in _fingerprint_sources(workspace):
        stat = path.stat()
        sources.append(
            {
                "path": path.relative_to(workspace).as_posix(),
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
        )
    payload = {
        "standard_id": standard.id,
        "standard_version": standard.version,
        "manifest_digest": _file_digest(workspace / "codex-bridge.yaml"),
        "sources": sources,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _fingerprint_sources(workspace: Path) -> tuple[Path, ...]:
    patterns = (
        "codex-bridge.yaml",
        "specs/*/spec.md",
        "specs/*/plan.md",
        "specs/*/tasks.md",
        "specs/*/traceability.yaml",
        "specs/*/diagrams/*.mmd",
        "specs/*/diagrams/*.yaml",
        "architecture/*.mmd",
        "architecture/*.yaml",
    )
    paths: list[Path] = []
    for pattern in patterns:
        paths.extend(
            path.resolve()
            for path in workspace.glob(pattern)
            if path.is_file() and _is_relative_to(path.resolve(), workspace)
        )
    return tuple(sorted(set(paths), key=lambda item: item.as_posix()))


def _spec_entries(workspace: Path) -> dict[str, dict[str, str]]:
    entries: dict[str, dict[str, str]] = {}
    for spec_path in sorted(workspace.glob("specs/*/spec.md")):
        if not spec_path.is_file():
            continue
        prefix = _read_prefix(spec_path)
        spec_id = spec_path.parent.name
        entries[spec_id] = {
            "path": spec_path.relative_to(workspace).as_posix(),
            "title": _first_markdown_heading(prefix) or spec_id,
            "status": _front_matter_value(prefix, "status") or "unknown",
            "summary": _summary_from_prefix(prefix),
        }
    return entries


def _diagram_entries(workspace: Path) -> dict[str, dict[str, str]]:
    entries: dict[str, dict[str, str]] = {}
    for diagram_path in sorted(
        [
            *workspace.glob("architecture/*.mmd"),
            *workspace.glob("specs/*/diagrams/*.mmd"),
        ]
    ):
        if not diagram_path.is_file():
            continue
        relative = diagram_path.relative_to(workspace).as_posix()
        metadata = _read_optional_yaml(diagram_path.with_suffix(".yaml"))
        entries[_index_key(relative)] = {
            "path": relative,
            "diagram_type": str(metadata.get("diagram_type") or "unknown"),
            "scope": str(metadata.get("scope") or _diagram_scope(relative)),
            "metadata_path": diagram_path.with_suffix(".yaml")
            .relative_to(workspace)
            .as_posix()
            if diagram_path.with_suffix(".yaml").is_file()
            else "",
        }
    return entries


def _module_entries(manifest: dict[str, Any]) -> dict[str, dict[str, str]]:
    sdd = manifest.get("sdd")
    if not isinstance(sdd, dict):
        return {}
    context_rules = sdd.get("context_rules")
    if not isinstance(context_rules, dict):
        return {}
    domains = context_rules.get("domains")
    if not isinstance(domains, dict):
        return {}
    entries: dict[str, dict[str, str]] = {}
    for domain_name, rules in domains.items():
        if not isinstance(domain_name, str) or not isinstance(rules, dict):
            continue
        modules = rules.get("modules")
        preferred_context = rules.get("preferred_context")
        entries[domain_name] = {
            "modules": ", ".join(modules) if _is_string_list(modules) else "",
            "preferred_context": ", ".join(preferred_context)
            if _is_string_list(preferred_context)
            else "",
        }
    return entries


def _candidate_limits(manifest: dict[str, Any]) -> dict[str, int]:
    sdd = manifest.get("sdd")
    if not isinstance(sdd, dict):
        return {"related_specs": 5, "related_diagrams": 3}
    context_rules = sdd.get("context_rules")
    if not isinstance(context_rules, dict):
        return {"related_specs": 5, "related_diagrams": 3}
    candidate_limits = context_rules.get("candidate_limits")
    if not isinstance(candidate_limits, dict):
        return {"related_specs": 5, "related_diagrams": 3}
    return {
        "related_specs": candidate_limits.get("related_specs", 5)
        if isinstance(candidate_limits.get("related_specs"), int)
        else 5,
        "related_diagrams": candidate_limits.get("related_diagrams", 3)
        if isinstance(candidate_limits.get("related_diagrams"), int)
        else 3,
    }


def _read_manifest(workspace: Path) -> dict[str, Any]:
    manifest_path = workspace / "codex-bridge.yaml"
    try:
        manifest = parse_simple_yaml(manifest_path.read_text(encoding="utf-8"))
    except SddStandardError:
        return {}
    return manifest if isinstance(manifest, dict) else {}


def _read_optional_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = parse_simple_yaml(path.read_text(encoding="utf-8"))
    except SddStandardError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _index_fingerprint(path: Path) -> str | None:
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("fingerprint:"):
            return line.partition(":")[2].strip().strip('"')
    return None


def _file_digest(path: Path) -> str:
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_prefix(path: Path) -> str:
    with path.open("rb") as handle:
        return handle.read(SPEC_PREFIX_BYTES).decode("utf-8", errors="replace")


def _first_markdown_heading(content: str) -> str | None:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or None
    return None


def _front_matter_value(content: str, key: str) -> str | None:
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        stripped = line.strip()
        if stripped == "---":
            return None
        raw_key, separator, raw_value = stripped.partition(":")
        if separator and raw_key.strip() == key:
            return raw_value.strip() or None
    return None


def _summary_from_prefix(content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and stripped != "---":
            return stripped[:240]
    return ""


def _diagram_scope(relative_path: str) -> str:
    return "baseline" if relative_path.startswith("architecture/") else "feature"


def _index_key(relative_path: str) -> str:
    return relative_path.replace("/", "__").replace(".", "_")


def _dump_yaml(value: Any, *, indent: int = 0) -> str:
    lines: list[str] = []
    _write_yaml_lines(lines, value, indent=indent)
    return "\n".join(lines) + "\n"


def _write_yaml_lines(lines: list[str], value: Any, *, indent: int) -> None:
    prefix = " " * indent
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, dict):
                lines.append(f"{prefix}{key}:")
                _write_yaml_lines(lines, item, indent=indent + 2)
            elif isinstance(item, (list, tuple)):
                lines.append(f"{prefix}{key}:")
                for entry in item:
                    lines.append(f"{prefix}  - {_yaml_scalar(entry)}")
            else:
                lines.append(f"{prefix}{key}: {_yaml_scalar(item)}")
        return
    lines.append(f"{prefix}{_yaml_scalar(value)}")


def _yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    text = str(value)
    if not text:
        return '""'
    if any(char in text for char in ":#[]{}&,*!|>'\"%@`") or text.strip() != text:
        return json.dumps(text)
    return text


def _is_string_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
