from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.app.application.services.sdd_index_service import SddIndexService
from backend.app.application.services.sdd_standard_service import (
    SddStandard,
    SddStandardError,
    parse_simple_yaml,
)


CONTEXT_PACK_PRESETS = (
    "new-feature",
    "modify-existing-feature",
    "bugfix",
    "architecture-change",
    "data-model-change",
    "domain-model-change",
    "implementation-from-spec",
    "diagram-update",
    "sdd-audit",
)


@dataclass(frozen=True, slots=True)
class SddContextCandidate:
    path: str
    reason: str
    rank: int


@dataclass(frozen=True, slots=True)
class SddContextPack:
    preset: str
    status: str
    mode: str
    index_status: str
    required_files: tuple[str, ...] = ()
    related_specs: tuple[SddContextCandidate, ...] = ()
    related_diagrams: tuple[SddContextCandidate, ...] = ()
    blocked_reads: tuple[str, ...] = ()
    routing_decisions: tuple[str, ...] = ()
    next_actions: tuple[str, ...] = ()


class SddContextPackService:
    def __init__(self, index_service: SddIndexService | None = None) -> None:
        self._index_service = index_service or SddIndexService()

    def build_pack(
        self,
        workspace: Path,
        *,
        standard: SddStandard,
        preset: str,
        selected_artifact: str | None = None,
        query: str = "",
        auto_regenerate_indexes: bool = True,
        allow_degraded: bool = True,
    ) -> SddContextPack:
        workspace = workspace.expanduser().resolve()
        if preset not in CONTEXT_PACK_PRESETS:
            return _blocked_pack(
                preset=preset,
                index_status="not_checked",
                reason=f"Unsupported context pack preset: {preset}",
            )
        manifest = _read_manifest(workspace)
        manifest_error = _context_rules_error(manifest, standard)
        if manifest_error is not None:
            return _blocked_pack(
                preset=preset,
                index_status="not_checked",
                reason=manifest_error,
            )
        index_status = self._index_service.ensure_indexes(
            workspace,
            standard=standard,
            auto_regenerate=auto_regenerate_indexes,
            allow_degraded=allow_degraded,
        )
        if index_status.mode == "hard_failure":
            return _blocked_pack(
                preset=preset,
                index_status=index_status.state,
                reason=index_status.detail,
            )
        base_required = _required_files_for_preset(
            preset,
            manifest=manifest,
            selected_artifact=selected_artifact,
        )
        if index_status.state == "failed":
            return SddContextPack(
                preset=preset,
                status="degraded" if index_status.mode == "degraded" else "blocked",
                mode=index_status.mode,
                index_status=index_status.state,
                required_files=base_required,
                blocked_reads=_blocked_reads(),
                routing_decisions=(
                    "Index regeneration failed; returning required baseline context only.",
                ),
                next_actions=(
                    "Regenerate .sdd indexes before related-candidate routing.",
                ),
            )

        indexes = _read_indexes(workspace)
        limits = _context_limits(manifest, standard)
        related_specs = _rank_specs(
            indexes.get("specs", {}),
            query=query,
            selected_artifact=selected_artifact,
            limit=limits["related_specs"],
        )
        related_diagrams = _rank_diagrams(
            indexes.get("diagrams", {}),
            query=query,
            selected_artifact=selected_artifact,
            limit=limits["related_diagrams"],
        )
        selected_requirement_error = _selected_artifact_error(
            preset,
            selected_artifact,
            indexes,
        )
        if selected_requirement_error is not None:
            return _blocked_pack(
                preset=preset,
                index_status=index_status.state,
                reason=selected_requirement_error,
            )
        return SddContextPack(
            preset=preset,
            status="ready",
            mode="normal",
            index_status=index_status.state,
            required_files=base_required,
            related_specs=related_specs,
            related_diagrams=related_diagrams,
            blocked_reads=_blocked_reads(),
            routing_decisions=(
                "Resolved context rules with precedence Workbench default -> project profile -> project overrides.",
                f"Applied limits related_specs={limits['related_specs']} related_diagrams={limits['related_diagrams']}.",
                "Candidates ranked deterministically from .sdd indexes only.",
            ),
        )


def _blocked_pack(*, preset: str, index_status: str, reason: str) -> SddContextPack:
    return SddContextPack(
        preset=preset,
        status="blocked",
        mode="hard_failure",
        index_status=index_status,
        blocked_reads=_blocked_reads(),
        routing_decisions=(reason,),
        next_actions=("Fix the blocking condition before building a context pack.",),
    )


def _blocked_reads() -> tuple[str, ...]:
    return (
        "read_all_specs_without_context_pack",
        "scan_every_full_spec_body",
        "fallback_to_all_specs_when_indexes_unavailable",
    )


def _required_files_for_preset(
    preset: str,
    *,
    manifest: dict[str, Any],
    selected_artifact: str | None,
) -> tuple[str, ...]:
    common = [
        "codex-bridge.yaml",
        "standard_payload",
        ".specify/memory/constitution.md",
    ]
    if Path("architecture/overview.md").as_posix():
        overview = "architecture/overview.md"
    else:
        overview = ""
    if preset == "new-feature":
        return _required_tuple([*common, ".sdd/context-index.yaml", overview])
    if preset in {"modify-existing-feature", "implementation-from-spec"}:
        spec_root = _selected_spec_root(selected_artifact)
        if spec_root is None:
            return tuple(common)
        return _required_tuple(
            [
                *common,
                f"{spec_root}/spec.md",
                f"{spec_root}/plan.md",
                f"{spec_root}/tasks.md",
                f"{spec_root}/traceability.yaml",
            ]
        )
    if preset == "bugfix":
        return _required_tuple(
            [*common, ".sdd/module-index.yaml", selected_artifact or ""]
        )
    if preset == "architecture-change":
        return _required_tuple(
            [*common, overview, *_protected_baselines(manifest), "architecture/adrs/"]
        )
    if preset == "data-model-change":
        return _required_tuple([*common, "data/persistence-model.md", "data/model.md"])
    if preset == "domain-model-change":
        return _required_tuple([*common, "domain/glossary.md", "domain/model.md"])
    if preset == "diagram-update":
        return _required_tuple(
            [*common, selected_artifact or "", _metadata_for(selected_artifact)]
        )
    if preset == "sdd-audit":
        return _required_tuple(
            [
                *common,
                ".sdd/spec-index.yaml",
                ".sdd/diagram-index.yaml",
                ".sdd/context-index.yaml",
                overview,
            ]
        )
    return _required_tuple(common)


def _required_tuple(paths: list[str]) -> tuple[str, ...]:
    return tuple(path for path in paths if path)


def _selected_artifact_error(
    preset: str,
    selected_artifact: str | None,
    indexes: dict[str, dict[str, Any]],
) -> str | None:
    if preset in {
        "modify-existing-feature",
        "implementation-from-spec",
        "diagram-update",
    }:
        if not selected_artifact:
            return f"{preset} requires selected_artifact."
    if preset == "diagram-update":
        diagram_paths = {
            str(item.get("path"))
            for item in indexes.get("diagrams", {}).values()
            if isinstance(item, dict)
        }
        if selected_artifact not in diagram_paths:
            return (
                f"Selected diagram is not present in diagram-index: {selected_artifact}"
            )
    return None


def _rank_specs(
    specs: dict[str, Any],
    *,
    query: str,
    selected_artifact: str | None,
    limit: int,
) -> tuple[SddContextCandidate, ...]:
    candidates: list[tuple[int, str, str]] = []
    terms = _terms(query)
    selected_root = _selected_spec_root(selected_artifact)
    for spec_id, raw in specs.items():
        if not isinstance(raw, dict):
            continue
        path = str(raw.get("path") or "")
        haystack = " ".join(
            str(raw.get(key) or "") for key in ("path", "title", "summary", "status")
        ).lower()
        score = sum(1 for term in terms if term in haystack)
        if selected_root and path.startswith(selected_root + "/"):
            score += 100
        reason = "selected artifact" if score >= 100 else "query/index match"
        candidates.append((-score, path or str(spec_id), reason))
    candidates.sort(key=lambda item: (item[0], item[1]))
    return tuple(
        SddContextCandidate(path=path, reason=reason, rank=index + 1)
        for index, (_score, path, reason) in enumerate(candidates[:limit])
    )


def _rank_diagrams(
    diagrams: dict[str, Any],
    *,
    query: str,
    selected_artifact: str | None,
    limit: int,
) -> tuple[SddContextCandidate, ...]:
    candidates: list[tuple[int, str, str]] = []
    terms = _terms(query)
    for diagram_id, raw in diagrams.items():
        if not isinstance(raw, dict):
            continue
        path = str(raw.get("path") or "")
        haystack = " ".join(
            str(raw.get(key) or "") for key in ("path", "diagram_type", "scope")
        ).lower()
        score = sum(1 for term in terms if term in haystack)
        if selected_artifact and path == selected_artifact:
            score += 100
        reason = "selected artifact" if score >= 100 else "query/index match"
        candidates.append((-score, path or str(diagram_id), reason))
    candidates.sort(key=lambda item: (item[0], item[1]))
    return tuple(
        SddContextCandidate(path=path, reason=reason, rank=index + 1)
        for index, (_score, path, reason) in enumerate(candidates[:limit])
    )


def _read_indexes(workspace: Path) -> dict[str, dict[str, Any]]:
    spec_index = _read_yaml_mapping(workspace / ".sdd/spec-index.yaml")
    diagram_index = _read_yaml_mapping(workspace / ".sdd/diagram-index.yaml")
    module_index = _read_yaml_mapping(workspace / ".sdd/module-index.yaml")
    return {
        "specs": spec_index.get("specs")
        if isinstance(spec_index.get("specs"), dict)
        else {},
        "diagrams": diagram_index.get("diagrams")
        if isinstance(diagram_index.get("diagrams"), dict)
        else {},
        "modules": module_index.get("modules")
        if isinstance(module_index.get("modules"), dict)
        else {},
    }


def _context_limits(manifest: dict[str, Any], standard: SddStandard) -> dict[str, int]:
    limits = {"related_specs": 5, "related_diagrams": 3}
    standard_limits = standard.payload.get("candidate_limits")
    if isinstance(standard_limits, dict):
        limits.update(
            {
                key: value
                for key, value in standard_limits.items()
                if isinstance(value, int)
            }
        )
    sdd = manifest.get("sdd")
    context_rules = sdd.get("context_rules") if isinstance(sdd, dict) else None
    candidate_limits = (
        context_rules.get("candidate_limits")
        if isinstance(context_rules, dict)
        else None
    )
    if isinstance(candidate_limits, dict):
        for key in ("related_specs", "related_diagrams"):
            value = candidate_limits.get(key)
            if isinstance(value, int) and value >= 0:
                limits[key] = min(value, limits[key])
    return limits


def _context_rules_error(
    manifest: dict[str, Any],
    standard: SddStandard,
) -> str | None:
    sdd = manifest.get("sdd")
    if not isinstance(sdd, dict):
        return "Missing sdd manifest block."
    context_rules = sdd.get("context_rules")
    if context_rules is None:
        return None
    if not isinstance(context_rules, dict):
        return "sdd.context_rules must be a mapping."
    allowed = _allowed_context_rule_keys(standard)
    unknown = sorted(set(context_rules) - allowed)
    if unknown:
        return "Unsupported sdd.context_rules key(s): " + ", ".join(unknown)
    return None


def _allowed_context_rule_keys(standard: SddStandard) -> set[str]:
    context_rules = standard.payload.get("context_rules")
    if not isinstance(context_rules, dict):
        return set()
    allowed = context_rules.get("allowed_override_keys")
    if not isinstance(allowed, list):
        return set()
    return {item for item in allowed if isinstance(item, str)}


def _read_manifest(workspace: Path) -> dict[str, Any]:
    return _read_yaml_mapping(workspace / "codex-bridge.yaml")


def _read_yaml_mapping(path: Path) -> dict[str, Any]:
    try:
        payload = parse_simple_yaml(path.read_text(encoding="utf-8"))
    except (OSError, SddStandardError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _terms(query: str) -> tuple[str, ...]:
    return tuple(term for term in query.lower().replace("/", " ").split() if term)


def _selected_spec_root(selected_artifact: str | None) -> str | None:
    if not selected_artifact or not selected_artifact.startswith("specs/"):
        return None
    parts = selected_artifact.split("/")
    if len(parts) < 2:
        return None
    return "/".join(parts[:2])


def _metadata_for(selected_artifact: str | None) -> str:
    if not selected_artifact or not selected_artifact.endswith(".mmd"):
        return ""
    return selected_artifact.removesuffix(".mmd") + ".yaml"


def _protected_baselines(manifest: dict[str, Any]) -> tuple[str, ...]:
    sdd = manifest.get("sdd")
    if not isinstance(sdd, dict):
        return ()
    protected = sdd.get("protected_baseline")
    if not isinstance(protected, list):
        return ()
    return tuple(item for item in protected if isinstance(item, str))
