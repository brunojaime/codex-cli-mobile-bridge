from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from backend.app.application.services.sdd_context_pack_service import (
    SddContextPack,
    SddContextPackService,
)
from backend.app.application.services.sdd_standard_service import (
    DEFAULT_STANDARD_ID,
    SddStandard,
    SddStandardError,
    SddStandardService,
    parse_simple_yaml,
)


@dataclass(frozen=True, slots=True)
class SddLlmInstructionResult:
    status: str
    prompt: str
    context_pack: SddContextPack | None
    error: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "prompt": self.prompt,
            "context_pack": asdict(self.context_pack) if self.context_pack else None,
            "error": self.error,
        }


class SddLlmInstructionService:
    def __init__(
        self,
        *,
        standard_service: SddStandardService | None = None,
        context_pack_service: SddContextPackService | None = None,
    ) -> None:
        self._standard_service = standard_service or SddStandardService()
        self._context_pack_service = context_pack_service or SddContextPackService()

    def build_prompt(
        self,
        workspace: Path,
        *,
        preset: str,
        selected_artifact: str | None = None,
        query: str = "",
        auto_regenerate_indexes: bool = True,
        allow_degraded: bool = True,
    ) -> SddLlmInstructionResult:
        workspace = workspace.expanduser().resolve()
        standard_id, manifest_error = _manifest_standard_id(workspace)
        if manifest_error is not None:
            return _blocked_result(manifest_error)
        try:
            standard = self._standard_service.load(standard_id or DEFAULT_STANDARD_ID)
            standard_resolution = self._standard_service.llm_resolution_instructions(
                standard.requested_id
            )
        except SddStandardError as exc:
            return _blocked_result(str(exc))
        context_pack = self._context_pack_service.build_pack(
            workspace,
            standard=standard,
            preset=preset,
            selected_artifact=selected_artifact,
            query=query,
            auto_regenerate_indexes=auto_regenerate_indexes,
            allow_degraded=allow_degraded,
        )
        prompt = _build_prompt_text(
            workspace=workspace,
            standard=standard,
            standard_resolution=standard_resolution,
            context_pack=context_pack,
            protected_baselines=_protected_baselines(workspace),
        )
        return SddLlmInstructionResult(
            status=context_pack.status,
            prompt=prompt,
            context_pack=context_pack,
            error=None
            if context_pack.status != "blocked"
            else context_pack.routing_decisions[0],
        )


def _blocked_result(reason: str) -> SddLlmInstructionResult:
    return SddLlmInstructionResult(
        status="blocked",
        prompt=(
            "Workbench SDD action blocked.\n"
            f"Reason: {reason}\n"
            "Do not proceed with implementation or broad file reads until this is fixed."
        ),
        context_pack=None,
        error=reason,
    )


def _build_prompt_text(
    *,
    workspace: Path,
    standard: SddStandard,
    standard_resolution: str,
    context_pack: SddContextPack,
    protected_baselines: tuple[str, ...],
) -> str:
    lines = [
        "Workbench SDD Codex Action",
        "",
        f"workspace_path: {workspace}",
        f"standard_payload: {standard.id}",
        f"standard_payload_source: {standard.source_path}",
        "",
        "Standard resolution:",
        standard_resolution,
        "",
        f"context_pack_preset: {context_pack.preset}",
        f"context_pack_status: {context_pack.status}",
        f"context_pack_mode: {context_pack.mode}",
        f"index_status: {context_pack.index_status}",
        "",
        "Required first reads:",
        "- codex-bridge.yaml",
        "- standard_payload",
        "- .specify/memory/constitution.md",
        "- .sdd/context-index.yaml when present in required_files",
        "- Only files listed in required_files or selected candidates below",
        "",
        "Required files:",
        *_bullet_lines(context_pack.required_files),
        "",
        "Related specs:",
        *_candidate_lines(context_pack.related_specs),
        "",
        "Related diagrams:",
        *_candidate_lines(context_pack.related_diagrams),
        "",
        "Blocked reads:",
        *_bullet_lines(context_pack.blocked_reads),
        "- Do not read all specs unless a future context pack explicitly permits it.",
        "- Do not scan every full spec body as fallback.",
        "",
        "Routing decisions:",
        *_bullet_lines(context_pack.routing_decisions),
        "",
        "Baseline protection:",
        "- Protect baseline architecture, domain, and data artifacts.",
        "- Do not edit protected baseline diagrams without explicit impact policy and task coverage.",
        *_bullet_lines(protected_baselines),
        "",
        "Project-owned rules:",
        "- Preserve domain language, project-owned context rules, and stricter sdd.context_rules overrides.",
        "- Workbench rules define process; project artifacts define domain truth.",
        "",
        "Next actions:",
        *_bullet_lines(context_pack.next_actions),
    ]
    return "\n".join(lines).strip()


def _bullet_lines(values: tuple[str, ...]) -> list[str]:
    if not values:
        return ["- none"]
    return [f"- {value}" for value in values]


def _candidate_lines(candidates: tuple[Any, ...]) -> list[str]:
    if not candidates:
        return ["- none"]
    return [
        f"- rank={candidate.rank} path={candidate.path} reason={candidate.reason}"
        for candidate in candidates
    ]


def _manifest_standard_id(workspace: Path) -> tuple[str | None, str | None]:
    manifest_path = workspace / "codex-bridge.yaml"
    if not manifest_path.is_file():
        return None, "Missing codex-bridge.yaml."
    try:
        manifest = parse_simple_yaml(manifest_path.read_text(encoding="utf-8"))
    except SddStandardError as exc:
        return None, f"codex-bridge.yaml is not valid supported YAML: {exc}"
    if not isinstance(manifest, dict):
        return None, "codex-bridge.yaml must contain a mapping."
    sdd = manifest.get("sdd")
    if not isinstance(sdd, dict):
        return None, "Missing sdd manifest block."
    standard = sdd.get("standard")
    if not isinstance(standard, str):
        return None, "sdd.standard must be a string such as workbench-sdd/v1."
    return standard, None


def _protected_baselines(workspace: Path) -> tuple[str, ...]:
    manifest_path = workspace / "codex-bridge.yaml"
    try:
        manifest = parse_simple_yaml(manifest_path.read_text(encoding="utf-8"))
    except (OSError, SddStandardError):
        return ()
    if not isinstance(manifest, dict):
        return ()
    sdd = manifest.get("sdd")
    if not isinstance(sdd, dict):
        return ()
    protected = sdd.get("protected_baseline")
    if not isinstance(protected, list):
        return ()
    return tuple(item for item in protected if isinstance(item, str))
