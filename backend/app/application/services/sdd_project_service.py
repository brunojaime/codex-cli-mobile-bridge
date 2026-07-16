from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.app.application.services.sdd_standard_service import (
    SddStandardError,
    parse_simple_yaml,
)


ALLOWED_SDD_EXTENSIONS = frozenset({".md", ".mmd", ".yaml", ".yml", ".json"})
ALLOWED_RENDERED_DIAGRAM_EXTENSIONS = frozenset({".svg"})
DEFAULT_SDD_FILE_MAX_BYTES = 256_000
DEFAULT_SDD_SVG_MAX_BYTES = 512_000
ARCHIVED_SPEC_DIR_NAMES = frozenset({"archive", "archives", "_archive", ".archive"})


class SddProjectError(RuntimeError):
    pass


class SddWorkspacePathError(SddProjectError):
    pass


class SddSpecNotFoundError(SddProjectError):
    pass


@dataclass(frozen=True, slots=True)
class SddFile:
    path: str
    title: str | None
    size_bytes: int
    content: str | None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class SddDiagram:
    path: str
    title: str | None
    size_bytes: int
    content: str | None
    diagram_type: str
    scope: str
    error: str | None = None
    spec_id: str | None = None
    diagram_id: str | None = None
    source_format: str = "mermaid"
    rendered_format: str | None = None
    content_type: str = "text/plain; charset=utf-8"
    digest: str | None = None
    updated_at: str | None = None
    metadata_path: str | None = None
    renderer: str | None = None


@dataclass(frozen=True, slots=True)
class SddDiagramAsset:
    path: str
    content: str
    content_type: str
    digest: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class SddRenderedDiagramExport:
    workspace_path: str
    spec_id: str
    diagram_id: str
    title: str | None
    diagram_type: str
    svg: str
    renderer: str | None = None
    diagram_spec_id: str | None = None


@dataclass(frozen=True, slots=True)
class SddTaskNode:
    id: str
    title: str
    number: int
    status: str
    description: str
    file: SddFile | None
    diagrams: tuple[SddDiagram, ...]


@dataclass(frozen=True, slots=True)
class SddPlanNode:
    id: str
    title: str
    number: int
    status: str
    description: str
    file: SddFile | None
    diagrams: tuple[SddDiagram, ...]
    tasks: tuple[SddTaskNode, ...]


@dataclass(frozen=True, slots=True)
class SddSpecTree:
    file: SddFile | None
    diagrams: tuple[SddDiagram, ...]
    plans: tuple[SddPlanNode, ...]
    missing: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return not self.missing


@dataclass(frozen=True, slots=True)
class SddSpecTaskSummary:
    total: int
    completed: int
    pending: int


@dataclass(frozen=True, slots=True)
class SddSpecGeneratedMetadata:
    title: bool
    description: bool
    user_pinned_title: bool
    user_pinned_description: bool


@dataclass(frozen=True, slots=True)
class SddSpecMetadata:
    id: str
    title: str
    description: str
    lifecycle_status: str
    created_at: str | None
    updated_at: str | None
    generated: SddSpecGeneratedMetadata
    tasks: SddSpecTaskSummary
    last_run_state: str | None
    metadata_status: str
    metadata_warnings: tuple[str, ...]
    metadata_stale_paths: tuple[str, ...]
    available_files: tuple[str, ...]
    diagrams: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SddSpec:
    id: str
    title: str
    path: str
    spec: SddFile | None
    plan: SddFile | None
    tasks: SddFile | None
    spec_files: tuple[SddFile, ...]
    plan_files: tuple[SddFile, ...]
    task_files: tuple[SddFile, ...]
    slice_docs: tuple[SddFile, ...]
    diagrams: tuple[SddDiagram, ...]
    tree: SddSpecTree | None
    missing: tuple[str, ...]
    metadata: SddSpecMetadata


@dataclass(frozen=True, slots=True)
class SddProject:
    workspace_name: str
    workspace_path: str
    required: bool
    manifest: SddFile | None
    constitution: SddFile | None
    architecture_diagrams: tuple[SddDiagram, ...]
    specs: tuple[SddSpec, ...]
    missing_required: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SddProjectSummary:
    workspace_name: str
    workspace_path: str
    has_manifest: bool
    has_constitution: bool
    spec_count: int
    diagram_count: int
    missing_required: tuple[str, ...]


class SddProjectService:
    def __init__(
        self,
        *,
        projects_root: str,
        workspace_aliases: dict[str, str] | None = None,
        file_max_bytes: int = DEFAULT_SDD_FILE_MAX_BYTES,
    ) -> None:
        self._projects_root = Path(projects_root).expanduser().resolve()
        self._workspace_aliases = {
            key: Path(value).expanduser().resolve()
            for key, value in (workspace_aliases or {}).items()
            if key.strip() and str(value).strip()
        }
        self._normalized_workspace_aliases = {
            _normalize_workspace_alias_key(key): value
            for key, value in self._workspace_aliases.items()
            if _normalize_workspace_alias_key(key)
        }
        self._file_max_bytes = file_max_bytes

    def list_projects(self) -> tuple[SddProjectSummary, ...]:
        roots: list[Path] = []
        if self._projects_root.is_dir():
            for child in sorted(
                self._projects_root.iterdir(), key=lambda item: item.name
            ):
                if child.is_dir():
                    try:
                        root = self._validate_workspace_path(str(child))
                    except SddWorkspacePathError:
                        continue
                    if root not in roots:
                        roots.append(root)
        for alias_path in self._workspace_aliases.values():
            if alias_path.is_dir() and alias_path not in roots:
                roots.append(alias_path)
        return tuple(self._project_summary(root) for root in roots)

    def get_project(self, workspace_path: str) -> SddProject:
        return self._project_snapshot(self._validate_workspace_path(workspace_path))

    def get_project_summary(self, workspace_path: str) -> SddProject:
        return self._project_summary_snapshot(
            self._validate_workspace_path(workspace_path)
        )

    def get_spec(self, workspace_path: str, spec_id: str) -> SddSpec:
        workspace = self._validate_workspace_path(workspace_path)
        specs_root = self._specs_root(workspace)
        feature_dir = self._resolve_spec_dir(workspace, specs_root, spec_id)
        return self._read_spec(workspace, specs_root, feature_dir)

    def list_spec_metadata(self, workspace_path: str) -> tuple[SddSpecMetadata, ...]:
        project = self.get_project(workspace_path)
        return tuple(spec.metadata for spec in project.specs)

    def get_spec_metadata(self, workspace_path: str, spec_id: str) -> SddSpecMetadata:
        for metadata in self.list_spec_metadata(workspace_path):
            if metadata.id == spec_id:
                return metadata
        raise SddSpecNotFoundError(f"Spec not found: {spec_id}")

    def get_diagrams(self, workspace_path: str) -> tuple[SddDiagram, ...]:
        workspace = self._validate_workspace_path(workspace_path)
        diagrams = list(
            self._read_diagrams(workspace, "architecture", scope="architecture")
        )
        specs_root = self._specs_root(workspace)
        if specs_root is not None:
            for raw_feature_dir in sorted(
                _safe_iterdir(specs_root),
                key=lambda item: item.name,
            ):
                feature_dir = _safe_resolve(raw_feature_dir)
                if not self._is_valid_spec_dir(workspace, specs_root, feature_dir):
                    continue
                rel_dir = feature_dir.relative_to(workspace).as_posix()
                diagrams.extend(
                    self._read_diagrams(
                        workspace,
                        f"{rel_dir}/diagrams",
                        scope=feature_dir.name,
                    )
                )
                diagrams.extend(
                    self._read_tree_diagrams_light(
                        workspace=workspace,
                        rel_dir=rel_dir,
                        scope=feature_dir.name,
                    )
                )
        return _unique_diagrams(tuple(diagrams))

    def get_diagram_asset(
        self,
        workspace_path: str,
        diagram_path: str,
    ) -> SddDiagramAsset:
        workspace = self._validate_workspace_path(workspace_path)
        resolved = self._resolve_rendered_diagram_path(workspace, diagram_path)
        stat = resolved.stat()
        if stat.st_size > DEFAULT_SDD_SVG_MAX_BYTES:
            raise SddProjectError("Rendered diagram is too large.")
        content = resolved.read_text(encoding="utf-8", errors="replace")
        if not _is_safe_svg_content(content):
            raise SddProjectError("Rendered diagram is not a safe SVG artifact.")
        return SddDiagramAsset(
            path=resolved.relative_to(workspace).as_posix(),
            content=content,
            content_type="image/svg+xml; charset=utf-8",
            digest=_file_digest(resolved),
            updated_at=_file_updated_at(stat),
        )

    def persist_rendered_diagram(
        self,
        export: SddRenderedDiagramExport,
    ) -> SddDiagram:
        workspace = self._validate_workspace_path(export.workspace_path)
        specs_root = self._specs_root(workspace)
        if specs_root is None:
            raise SddSpecNotFoundError("No specs directory found.")
        spec_dir = self._resolve_spec_dir(workspace, specs_root, export.spec_id)
        diagrams_dir = spec_dir / "diagrams"
        diagrams_dir.mkdir(parents=True, exist_ok=True)
        if not _is_relative_to(diagrams_dir.resolve(), workspace):
            raise SddWorkspacePathError("Diagram export path escaped workspace.")

        diagram_id = _safe_diagram_id(export.diagram_id)
        svg_path = diagrams_dir / f"{diagram_id}.svg"
        metadata_path = diagrams_dir / f"{diagram_id}.yaml"
        svg_content = export.svg.strip()
        if not _is_safe_svg_content(svg_content):
            raise SddProjectError("Rendered diagram export must be safe SVG.")
        svg_path.write_text(svg_content + "\n", encoding="utf-8")

        title = (export.title or diagram_id.replace("-", " ").title()).strip()
        renderer = (export.renderer or "diagram-mcp-rendering-engine").strip()
        metadata_lines = [
            f"diagram_id: {diagram_id}",
            f"diagram_type: {export.diagram_type.strip() or 'uml-component-svg'}",
            f"title: {title}",
            "source_format: svg",
            "rendered_format: svg",
            f"renderer: {renderer}",
            f"source: {svg_path.relative_to(workspace).as_posix()}",
        ]
        if export.diagram_spec_id:
            metadata_lines.append(f"diagram_spec_id: {export.diagram_spec_id.strip()}")
        metadata_path.write_text("\n".join(metadata_lines) + "\n", encoding="utf-8")

        diagram = self._read_svg_diagram(
            workspace=workspace,
            path=svg_path,
            scope=spec_dir.name,
            spec_id=spec_dir.name,
            metadata_path=metadata_path,
        )
        if diagram is None:
            raise SddProjectError("Rendered diagram export could not be read back.")
        return diagram

    def _validate_workspace_path(self, workspace_path: str) -> Path:
        raw_path = workspace_path.strip()
        if not raw_path:
            raise SddWorkspacePathError("workspace_path is required.")
        alias_path = self._workspace_aliases.get(raw_path)
        if alias_path is None:
            alias_path = self._normalized_workspace_aliases.get(
                _normalize_workspace_alias_key(raw_path),
            )
        candidate = (
            alias_path if alias_path is not None else Path(raw_path).expanduser()
        )
        if not candidate.is_absolute():
            candidate = self._projects_root / candidate
        resolved = candidate.resolve()
        canonical_alias_path = self._normalized_workspace_aliases.get(
            _normalize_workspace_alias_key(resolved.name),
        )
        if canonical_alias_path is not None:
            resolved = canonical_alias_path
        if not self._is_allowed_workspace(resolved):
            raise SddWorkspacePathError(
                "workspace_path must resolve under PROJECTS_ROOT or a known alias."
            )
        if not resolved.is_dir():
            raise SddWorkspacePathError("workspace_path must point to a directory.")
        return resolved

    def _is_allowed_workspace(self, path: Path) -> bool:
        if _is_relative_to(path, self._projects_root):
            return True
        return any(
            path == alias_path for alias_path in self._workspace_aliases.values()
        )

    def _project_summary(self, workspace: Path) -> SddProjectSummary:
        architecture_diagram_count = len(
            self._list_allowed_files(workspace, "architecture", suffix=".mmd")
        )
        spec_count = 0
        spec_diagram_count = 0
        specs_root = _safe_resolve(workspace / "specs")
        if (
            specs_root is not None
            and _is_relative_to(specs_root, workspace)
            and specs_root.is_dir()
        ):
            for raw_feature_dir in _safe_iterdir(specs_root):
                feature_dir = _safe_resolve(raw_feature_dir)
                if feature_dir is None:
                    continue
                if not self._is_valid_spec_dir(workspace, specs_root, feature_dir):
                    continue
                rel_dir = feature_dir.relative_to(workspace).as_posix()
                if self._allowed_file_exists(workspace, f"{rel_dir}/spec.md"):
                    spec_count += 1
                spec_diagram_count += len(
                    self._list_allowed_files(
                        workspace,
                        f"{rel_dir}/diagrams",
                        suffix=".mmd",
                    )
                )
        missing_required = list[str]()
        has_manifest = self._allowed_file_exists(workspace, "codex-bridge.yaml")
        has_constitution = self._allowed_file_exists(
            workspace,
            ".specify/memory/constitution.md",
        )
        diagram_count = architecture_diagram_count + spec_diagram_count
        if not has_manifest:
            missing_required.append("codex-bridge.yaml")
        if not has_constitution:
            missing_required.append(".specify/memory/constitution.md")
        if not spec_count:
            missing_required.append("specs/<feature>/spec.md")
        if not diagram_count:
            missing_required.append("*.mmd")
        return SddProjectSummary(
            workspace_name=workspace.name,
            workspace_path=str(workspace),
            has_manifest=has_manifest,
            has_constitution=has_constitution,
            spec_count=spec_count,
            diagram_count=diagram_count,
            missing_required=tuple(missing_required),
        )

    def _project_snapshot(self, workspace: Path) -> SddProject:
        manifest = self._read_optional_file(workspace, "codex-bridge.yaml")
        constitution = self._read_optional_file(
            workspace,
            ".specify/memory/constitution.md",
        )
        architecture_diagrams = self._read_diagrams(
            workspace,
            "architecture",
            scope="architecture",
        )
        specs = self._read_specs(workspace)
        missing_required = list[str]()
        if manifest is None:
            missing_required.append("codex-bridge.yaml")
        if constitution is None:
            missing_required.append(".specify/memory/constitution.md")
        if not specs:
            missing_required.append("specs/<feature>/spec.md")
        if not architecture_diagrams and not any(spec.diagrams for spec in specs):
            missing_required.append("*.mmd")
        return SddProject(
            workspace_name=workspace.name,
            workspace_path=str(workspace),
            required=True,
            manifest=manifest,
            constitution=constitution,
            architecture_diagrams=architecture_diagrams,
            specs=specs,
            missing_required=tuple(missing_required),
        )

    def _project_summary_snapshot(self, workspace: Path) -> SddProject:
        manifest = self._read_file_metadata(workspace, "codex-bridge.yaml")
        constitution = self._read_file_metadata(
            workspace,
            ".specify/memory/constitution.md",
        )
        architecture_diagrams = self._read_diagrams(
            workspace,
            "architecture",
            scope="architecture",
        )
        specs = self._read_spec_summaries(workspace)
        missing_required = list[str]()
        if manifest is None:
            missing_required.append("codex-bridge.yaml")
        if constitution is None:
            missing_required.append(".specify/memory/constitution.md")
        if not specs:
            missing_required.append("specs/<feature>/spec.md")
        if not architecture_diagrams and not any(spec.diagrams for spec in specs):
            missing_required.append("*.mmd")
        return SddProject(
            workspace_name=workspace.name,
            workspace_path=str(workspace),
            required=True,
            manifest=manifest,
            constitution=constitution,
            architecture_diagrams=architecture_diagrams,
            specs=specs,
            missing_required=tuple(missing_required),
        )

    def _read_specs(self, workspace: Path) -> tuple[SddSpec, ...]:
        specs_root = self._specs_root(workspace)
        if specs_root is None:
            return ()
        return tuple(
            self._read_spec(workspace, specs_root, feature_dir)
            for feature_dir in self._iter_spec_dirs(workspace, specs_root)
        )

    def _read_spec_summaries(self, workspace: Path) -> tuple[SddSpec, ...]:
        specs_root = self._specs_root(workspace)
        if specs_root is None:
            return ()
        return tuple(
            self._read_spec_summary(workspace, feature_dir)
            for feature_dir in self._iter_spec_dirs(workspace, specs_root)
        )

    def _specs_root(self, workspace: Path) -> Path | None:
        specs_root = _safe_resolve(workspace / "specs")
        if (
            specs_root is None
            or not _is_relative_to(specs_root, workspace)
            or not specs_root.is_dir()
        ):
            return None
        return specs_root

    def _iter_spec_dirs(self, workspace: Path, specs_root: Path) -> tuple[Path, ...]:
        specs: list[Path] = []
        for raw_feature_dir in sorted(
            _safe_iterdir(specs_root),
            key=lambda item: item.name,
        ):
            feature_dir = _safe_resolve(raw_feature_dir)
            if not self._is_valid_spec_dir(workspace, specs_root, feature_dir):
                continue
            specs.append(feature_dir)
        return tuple(specs)

    def _is_valid_spec_dir(
        self,
        workspace: Path,
        specs_root: Path,
        feature_dir: Path | None,
    ) -> bool:
        return (
            feature_dir is not None
            and feature_dir.is_dir()
            and _is_relative_to(feature_dir, specs_root)
            and _is_relative_to(feature_dir, workspace)
            and not _is_archived_spec_dir(feature_dir)
        )

    def _resolve_spec_dir(
        self,
        workspace: Path,
        specs_root: Path | None,
        spec_id: str,
    ) -> Path:
        raw_spec_id = spec_id.strip()
        if not raw_spec_id:
            raise SddSpecNotFoundError("spec_id is required.")
        if "/" in raw_spec_id or "\\" in raw_spec_id or ".." in Path(raw_spec_id).parts:
            raise SddSpecNotFoundError(f"Spec not found: {spec_id}")
        if specs_root is None:
            raise SddSpecNotFoundError(f"Spec not found: {spec_id}")
        feature_dir = _safe_resolve(specs_root / raw_spec_id)
        if not self._is_valid_spec_dir(workspace, specs_root, feature_dir):
            raise SddSpecNotFoundError(f"Spec not found: {spec_id}")
        return feature_dir

    def _read_spec(
        self,
        workspace: Path,
        specs_root: Path,
        feature_dir: Path,
    ) -> SddSpec:
        rel_dir = feature_dir.relative_to(workspace).as_posix()
        spec_file = self._read_optional_file(workspace, f"{rel_dir}/spec.md")
        plan_file = self._read_optional_file(workspace, f"{rel_dir}/plan.md")
        tasks_file = self._read_optional_file(workspace, f"{rel_dir}/tasks.md")
        spec_files = _with_primary(
            spec_file,
            self._read_history_files(
                workspace,
                rel_dir,
                history_dir="specs",
                root_prefix="spec",
                primary_name="spec.md",
            ),
        )
        plan_files = _with_primary(
            plan_file,
            self._read_history_files(
                workspace,
                rel_dir,
                history_dir="plans",
                root_prefix="plan",
                primary_name="plan.md",
            ),
        )
        task_files = _with_primary(
            tasks_file,
            self._read_history_files(
                workspace,
                rel_dir,
                history_dir="tasks",
                root_prefix="tasks",
                primary_name="tasks.md",
            ),
        )
        slice_docs = self._read_slice_docs(workspace, f"{rel_dir}/slices")
        diagrams = self._read_diagrams(
            workspace,
            f"{rel_dir}/diagrams",
            scope=feature_dir.name,
        )
        tree = self._read_spec_tree(
            workspace=workspace,
            rel_dir=rel_dir,
            scope=feature_dir.name,
            spec_file=spec_file,
        )
        diagrams = _unique_diagrams((*diagrams, *_tree_diagrams(tree)))
        if tree is None:
            missing = [
                filename
                for filename, file_value in (
                    ("spec.md", spec_file),
                    ("plan.md", plan_file),
                    ("tasks.md", tasks_file),
                )
                if file_value is None
            ]
        else:
            missing = list(tree.missing)
        return SddSpec(
            id=feature_dir.name,
            title=(
                spec_file.title if spec_file and spec_file.title else feature_dir.name
            ),
            path=rel_dir,
            spec=spec_file,
            plan=plan_file,
            tasks=tasks_file,
            spec_files=spec_files,
            plan_files=plan_files,
            task_files=task_files,
            slice_docs=slice_docs,
            diagrams=diagrams,
            tree=tree,
            missing=tuple(missing),
            metadata=self._read_spec_metadata(
                workspace=workspace,
                spec_id=feature_dir.name,
                rel_dir=rel_dir,
                spec_file=spec_file,
                plan_file=plan_file,
                tasks_file=tasks_file,
                diagrams=diagrams,
            ),
        )

    def _read_spec_summary(self, workspace: Path, feature_dir: Path) -> SddSpec:
        rel_dir = feature_dir.relative_to(workspace).as_posix()
        spec_file = self._read_optional_file(workspace, f"{rel_dir}/spec.md")
        plan_file = self._read_file_metadata(workspace, f"{rel_dir}/plan.md")
        tasks_file = self._read_file_metadata(workspace, f"{rel_dir}/tasks.md")
        tree = self._read_spec_tree_summary(
            workspace=workspace,
            rel_dir=rel_dir,
            scope=feature_dir.name,
            spec_file=spec_file,
        )
        diagrams = _unique_diagrams(
            (
                *self._read_diagrams(
                    workspace,
                    f"{rel_dir}/diagrams",
                    scope=feature_dir.name,
                ),
                *_tree_diagrams(tree),
            )
        )
        if tree is None:
            missing = [
                filename
                for filename, file_value in (
                    ("spec.md", spec_file),
                    ("plan.md", plan_file),
                    ("tasks.md", tasks_file),
                )
                if file_value is None
            ]
        else:
            missing = list(tree.missing)
        return SddSpec(
            id=feature_dir.name,
            title=(spec_file.title if spec_file and spec_file.title else feature_dir.name),
            path=rel_dir,
            spec=spec_file,
            plan=plan_file,
            tasks=tasks_file,
            spec_files=(() if spec_file is None else (spec_file,)),
            plan_files=(() if plan_file is None else (plan_file,)),
            task_files=(() if tasks_file is None else (tasks_file,)),
            slice_docs=(),
            diagrams=diagrams,
            tree=tree,
            missing=tuple(missing),
            metadata=self._read_spec_metadata(
                workspace=workspace,
                spec_id=feature_dir.name,
                rel_dir=rel_dir,
                spec_file=spec_file,
                plan_file=plan_file,
                tasks_file=tasks_file,
                diagrams=diagrams,
            ),
        )

    def _read_spec_tree(
        self,
        *,
        workspace: Path,
        rel_dir: str,
        scope: str,
        spec_file: SddFile | None,
    ) -> SddSpecTree | None:
        tree_file = self._read_optional_file(workspace, f"{rel_dir}/tree.json")
        if tree_file is None:
            tree_file = self._read_optional_file(workspace, f"{rel_dir}/tree.yaml")
        if tree_file is None or tree_file.error is not None:
            return None
        raw_content = tree_file.content or ""
        try:
            payload = (
                json.loads(raw_content)
                if tree_file.path.endswith(".json")
                else parse_simple_yaml(raw_content)
            )
        except (json.JSONDecodeError, SddStandardError):
            return None
        if not isinstance(payload, dict):
            return None
        spec_payload = payload.get("spec")
        spec_map = spec_payload if isinstance(spec_payload, dict) else {}
        missing: list[str] = []
        spec_path = _optional_str(spec_map.get("file")) or "spec.md"
        tree_spec_file = self._read_tree_file(
            workspace,
            rel_dir,
            spec_path,
        )
        resolved_spec_file = tree_spec_file or spec_file
        if resolved_spec_file is None:
            missing.append(_tree_path_label(rel_dir, spec_path, "spec.md"))
        plans: list[SddPlanNode] = []
        raw_plans = payload.get("plans")
        if isinstance(raw_plans, list):
            for index, raw_plan in enumerate(raw_plans):
                if not isinstance(raw_plan, dict):
                    continue
                plan, plan_missing = self._read_plan_node(
                    workspace=workspace,
                    rel_dir=rel_dir,
                    scope=scope,
                    payload=raw_plan,
                    fallback_number=index + 1,
                )
                plans.append(plan)
                missing.extend(plan_missing)
        if not plans:
            missing.append(f"{rel_dir}/tree.json: plans")
        return SddSpecTree(
            file=resolved_spec_file,
            diagrams=self._read_tree_diagrams(
                workspace,
                rel_dir,
                _string_items(spec_map.get("diagrams")),
                scope=scope,
            ),
            plans=tuple(plans),
            missing=tuple(missing),
        )

    def _read_spec_tree_summary(
        self,
        *,
        workspace: Path,
        rel_dir: str,
        scope: str,
        spec_file: SddFile | None,
    ) -> SddSpecTree | None:
        tree_file = self._read_optional_file(workspace, f"{rel_dir}/tree.json")
        if tree_file is None:
            tree_file = self._read_optional_file(workspace, f"{rel_dir}/tree.yaml")
        if tree_file is None or tree_file.error is not None:
            return None
        raw_content = tree_file.content or ""
        try:
            payload = (
                json.loads(raw_content)
                if tree_file.path.endswith(".json")
                else parse_simple_yaml(raw_content)
            )
        except (json.JSONDecodeError, SddStandardError):
            return None
        if not isinstance(payload, dict):
            return None
        spec_payload = payload.get("spec")
        spec_map = spec_payload if isinstance(spec_payload, dict) else {}
        missing: list[str] = []
        spec_path = _optional_str(spec_map.get("file")) or "spec.md"
        tree_spec_file = self._read_tree_file_metadata(
            workspace,
            rel_dir,
            spec_path,
        )
        resolved_spec_file = tree_spec_file or spec_file
        if resolved_spec_file is None:
            missing.append(_tree_path_label(rel_dir, spec_path, "spec.md"))
        plans: list[SddPlanNode] = []
        raw_plans = payload.get("plans")
        if isinstance(raw_plans, list):
            for index, raw_plan in enumerate(raw_plans):
                if not isinstance(raw_plan, dict):
                    continue
                plan, plan_missing = self._read_plan_node_summary(
                    workspace=workspace,
                    rel_dir=rel_dir,
                    scope=scope,
                    payload=raw_plan,
                    fallback_number=index + 1,
                )
                plans.append(plan)
                missing.extend(plan_missing)
        if not plans:
            missing.append(f"{rel_dir}/tree.json: plans")
        return SddSpecTree(
            file=resolved_spec_file,
            diagrams=self._read_tree_diagrams(
                workspace,
                rel_dir,
                _string_items(spec_map.get("diagrams")),
                scope=scope,
            ),
            plans=tuple(plans),
            missing=tuple(missing),
        )

    def _read_plan_node(
        self,
        *,
        workspace: Path,
        rel_dir: str,
        scope: str,
        payload: dict[str, object],
        fallback_number: int,
    ) -> tuple[SddPlanNode, tuple[str, ...]]:
        plan_number = _positive_int(payload.get("number"), fallback_number)
        plan_path = _optional_str(payload.get("file"))
        plan_file = self._read_tree_file(
            workspace,
            rel_dir,
            plan_path,
        )
        missing: list[str] = []
        if plan_file is None:
            missing.append(
                _tree_path_label(
                    rel_dir,
                    plan_path,
                    f"plan {plan_number} file",
                )
            )
        tasks: list[SddTaskNode] = []
        raw_tasks = payload.get("tasks")
        if isinstance(raw_tasks, list):
            for index, raw_task in enumerate(raw_tasks):
                if not isinstance(raw_task, dict):
                    continue
                task, task_missing = self._read_task_node(
                    workspace=workspace,
                    rel_dir=rel_dir,
                    scope=scope,
                    payload=raw_task,
                    fallback_number=index + 1,
                )
                tasks.append(task)
                missing.extend(task_missing)
        if not tasks:
            missing.append(f"plan {plan_number}: tasks")
        return (
            SddPlanNode(
                id=_tree_node_id(payload, f"plan-{plan_number}"),
                title=_tree_node_title(payload, plan_file, f"Plan {plan_number}"),
                number=plan_number,
                status=_tree_node_status(payload),
                description=_tree_node_description(payload),
                file=plan_file,
                diagrams=self._read_tree_diagrams(
                    workspace,
                    rel_dir,
                    _string_items(payload.get("diagrams")),
                    scope=f"{scope} / plan {plan_number}",
                ),
                tasks=tuple(tasks),
            ),
            tuple(missing),
        )

    def _read_plan_node_summary(
        self,
        *,
        workspace: Path,
        rel_dir: str,
        scope: str,
        payload: dict[str, object],
        fallback_number: int,
    ) -> tuple[SddPlanNode, tuple[str, ...]]:
        plan_number = _positive_int(payload.get("number"), fallback_number)
        plan_path = _optional_str(payload.get("file"))
        plan_file = self._read_tree_file_metadata(
            workspace,
            rel_dir,
            plan_path,
        )
        missing: list[str] = []
        if plan_file is None:
            missing.append(
                _tree_path_label(
                    rel_dir,
                    plan_path,
                    f"plan {plan_number} file",
                )
            )
        tasks: list[SddTaskNode] = []
        raw_tasks = payload.get("tasks")
        if isinstance(raw_tasks, list):
            for index, raw_task in enumerate(raw_tasks):
                if not isinstance(raw_task, dict):
                    continue
                task, task_missing = self._read_task_node_summary(
                    workspace=workspace,
                    rel_dir=rel_dir,
                    scope=scope,
                    payload=raw_task,
                    fallback_number=index + 1,
                )
                tasks.append(task)
                missing.extend(task_missing)
        if not tasks:
            missing.append(f"plan {plan_number}: tasks")
        return (
            SddPlanNode(
                id=_tree_node_id(payload, f"plan-{plan_number}"),
                title=_tree_node_title(payload, plan_file, f"Plan {plan_number}"),
                number=plan_number,
                status=_tree_node_status(payload),
                description=_tree_node_description(payload),
                file=plan_file,
                diagrams=self._read_tree_diagrams(
                    workspace,
                    rel_dir,
                    _string_items(payload.get("diagrams")),
                    scope=f"{scope} / plan {plan_number}",
                ),
                tasks=tuple(tasks),
            ),
            tuple(missing),
        )

    def _read_task_node(
        self,
        *,
        workspace: Path,
        rel_dir: str,
        scope: str,
        payload: dict[str, object],
        fallback_number: int,
    ) -> tuple[SddTaskNode, tuple[str, ...]]:
        task_number = _positive_int(payload.get("number"), fallback_number)
        task_path = _optional_str(payload.get("file"))
        task_file = self._read_tree_file(
            workspace,
            rel_dir,
            task_path,
        )
        missing = (
            (
                _tree_path_label(
                    rel_dir,
                    task_path,
                    f"task {task_number} file",
                ),
            )
            if task_file is None
            else ()
        )
        return (
            SddTaskNode(
                id=_tree_node_id(payload, f"task-{task_number}"),
                title=_tree_node_title(payload, task_file, f"Task {task_number}"),
                number=task_number,
                status=_tree_node_status(payload),
                description=_tree_node_description(payload),
                file=task_file,
                diagrams=self._read_tree_diagrams(
                    workspace,
                    rel_dir,
                    _string_items(payload.get("diagrams")),
                    scope=f"{scope} / task {task_number}",
                ),
            ),
            missing,
        )

    def _read_task_node_summary(
        self,
        *,
        workspace: Path,
        rel_dir: str,
        scope: str,
        payload: dict[str, object],
        fallback_number: int,
    ) -> tuple[SddTaskNode, tuple[str, ...]]:
        task_number = _positive_int(payload.get("number"), fallback_number)
        task_path = _optional_str(payload.get("file"))
        task_file = self._read_tree_file_metadata(
            workspace,
            rel_dir,
            task_path,
        )
        missing = (
            (
                _tree_path_label(
                    rel_dir,
                    task_path,
                    f"task {task_number} file",
                ),
            )
            if task_file is None
            else ()
        )
        return (
            SddTaskNode(
                id=_tree_node_id(payload, f"task-{task_number}"),
                title=_tree_node_title(payload, task_file, f"Task {task_number}"),
                number=task_number,
                status=_tree_node_status(payload),
                description=_tree_node_description(payload),
                file=task_file,
                diagrams=self._read_tree_diagrams(
                    workspace,
                    rel_dir,
                    _string_items(payload.get("diagrams")),
                    scope=f"{scope} / task {task_number}",
                ),
            ),
            missing,
        )

    def _read_tree_file(
        self,
        workspace: Path,
        rel_dir: str,
        relative_path: str | None,
    ) -> SddFile | None:
        if relative_path is None:
            return None
        path = relative_path.strip().lstrip("/")
        if not path or ".." in Path(path).parts:
            return None
        if path.startswith("specs/"):
            return self._read_optional_file(workspace, path)
        return self._read_optional_file(workspace, f"{rel_dir}/{path}")

    def _read_tree_file_metadata(
        self,
        workspace: Path,
        rel_dir: str,
        relative_path: str | None,
    ) -> SddFile | None:
        if relative_path is None:
            return None
        path = relative_path.strip().lstrip("/")
        if not path or ".." in Path(path).parts:
            return None
        if path.startswith("specs/"):
            return self._read_file_metadata(workspace, path)
        return self._read_file_metadata(workspace, f"{rel_dir}/{path}")

    def _read_tree_diagrams(
        self,
        workspace: Path,
        rel_dir: str,
        paths: tuple[str, ...],
        *,
        scope: str,
    ) -> tuple[SddDiagram, ...]:
        diagrams: list[SddDiagram] = []
        for item in paths:
            file_value = self._read_tree_file(workspace, rel_dir, item)
            if file_value is None:
                continue
            diagrams.append(
                SddDiagram(
                    path=file_value.path,
                    title=file_value.title,
                    size_bytes=file_value.size_bytes,
                    content=file_value.content,
                    diagram_type=_diagram_type(file_value.content),
                    scope=scope,
                    error=file_value.error,
                )
            )
        return tuple(diagrams)

    def _read_tree_diagrams_light(
        self,
        *,
        workspace: Path,
        rel_dir: str,
        scope: str,
    ) -> tuple[SddDiagram, ...]:
        tree = self._read_spec_tree_summary(
            workspace=workspace,
            rel_dir=rel_dir,
            scope=scope,
            spec_file=self._read_file_metadata(workspace, f"{rel_dir}/spec.md"),
        )
        return _tree_diagrams(tree)

    def _read_spec_metadata(
        self,
        *,
        workspace: Path,
        spec_id: str,
        rel_dir: str,
        spec_file: SddFile | None,
        plan_file: SddFile | None,
        tasks_file: SddFile | None,
        diagrams: tuple[SddDiagram, ...],
    ) -> SddSpecMetadata:
        metadata_file = self._read_optional_file(workspace, f"{rel_dir}/metadata.yaml")
        available_files = tuple(
            path
            for path, file_value in (
                (f"{rel_dir}/metadata.yaml", metadata_file),
                (f"{rel_dir}/spec.md", spec_file),
                (f"{rel_dir}/plan.md", plan_file),
                (f"{rel_dir}/tasks.md", tasks_file),
                (
                    f"{rel_dir}/traceability.yaml",
                    self._read_optional_file(workspace, f"{rel_dir}/traceability.yaml"),
                ),
            )
            if file_value is not None
        )
        diagram_paths = tuple(diagram.path for diagram in diagrams)
        parsed: dict[str, object] = {}
        warnings: list[str] = []
        metadata_status = "present"
        if metadata_file is None:
            metadata_status = "missing"
            warnings.append("metadata.yaml is missing; fallback metadata is used.")
        elif metadata_file.error is not None:
            metadata_status = "malformed"
            warnings.append(f"metadata.yaml could not be read: {metadata_file.error}")
        else:
            try:
                loaded = parse_simple_yaml(metadata_file.content or "")
            except SddStandardError as exc:
                loaded = None
                metadata_status = "malformed"
                warnings.append(f"metadata.yaml is malformed: {exc}")
            if isinstance(loaded, dict):
                parsed = loaded
            else:
                metadata_status = "malformed"
                warnings.append("metadata.yaml must contain a mapping.")

        task_summary = _task_summary_from_metadata_or_file(parsed, tasks_file)
        generated = _generated_metadata(parsed)
        stale_paths = _metadata_stale_paths(workspace, rel_dir, parsed)
        if stale_paths and metadata_status == "present":
            metadata_status = "stale"
            warnings.append("metadata.yaml source digests are stale.")

        return SddSpecMetadata(
            id=spec_id,
            title=str(parsed.get("title") or _fallback_title(spec_id, spec_file)),
            description=str(
                parsed.get("description") or _fallback_description(spec_file)
            ),
            lifecycle_status=str(parsed.get("status") or "draft"),
            created_at=_optional_str(parsed.get("created_at")),
            updated_at=_optional_str(parsed.get("updated_at")),
            generated=generated,
            tasks=task_summary,
            last_run_state=_optional_str(parsed.get("last_run_state")),
            metadata_status=metadata_status,
            metadata_warnings=tuple(warnings),
            metadata_stale_paths=stale_paths,
            available_files=available_files + diagram_paths,
            diagrams=diagram_paths,
        )

    def _read_history_files(
        self,
        workspace: Path,
        feature_rel_dir: str,
        *,
        history_dir: str,
        root_prefix: str,
        primary_name: str,
    ) -> tuple[SddFile, ...]:
        files: list[SddFile] = []
        seen: set[str] = set()
        for relative_dir in (feature_rel_dir, f"{feature_rel_dir}/{history_dir}"):
            for path in sorted(
                self._list_allowed_files(workspace, relative_dir, suffix=".md"),
                key=lambda item: item.name,
            ):
                if path.name == primary_name:
                    continue
                if relative_dir == feature_rel_dir and not path.name.startswith(
                    (f"{root_prefix}-", f"{root_prefix}_")
                ):
                    continue
                rel_path = path.relative_to(workspace).as_posix()
                if rel_path in seen:
                    continue
                file_value = self._read_optional_file(workspace, rel_path)
                if file_value is None:
                    continue
                seen.add(rel_path)
                files.append(file_value)
        return tuple(files)

    def _read_slice_docs(
        self,
        workspace: Path,
        relative_dir: str,
    ) -> tuple[SddFile, ...]:
        docs: list[SddFile] = []
        for path in sorted(
            self._list_allowed_files(workspace, relative_dir, suffix=".md"),
            key=lambda item: item.name,
        ):
            rel_path = path.relative_to(workspace).as_posix()
            file_value = self._read_optional_file(workspace, rel_path)
            if file_value is not None:
                docs.append(file_value)
        return tuple(docs)

    def _read_diagrams(
        self,
        workspace: Path,
        relative_dir: str,
        *,
        scope: str,
    ) -> tuple[SddDiagram, ...]:
        directory = _safe_resolve(workspace / relative_dir)
        if (
            directory is None
            or not _is_relative_to(directory, workspace)
            or not directory.is_dir()
        ):
            return ()
        diagrams: list[SddDiagram] = []
        spec_id = scope if relative_dir.startswith("specs/") else None
        for path in sorted(directory.glob("*.mmd"), key=lambda item: item.name):
            rel_path = path.relative_to(workspace).as_posix()
            file_value = self._read_optional_file(workspace, rel_path)
            if file_value is None:
                continue
            resolved = _safe_resolve(path)
            stat = resolved.stat() if resolved is not None and resolved.exists() else None
            diagrams.append(
                SddDiagram(
                    path=file_value.path,
                    title=file_value.title,
                    size_bytes=file_value.size_bytes,
                    content=file_value.content,
                    diagram_type=_diagram_type(file_value.content),
                    scope=scope,
                    error=file_value.error,
                    spec_id=spec_id,
                    diagram_id=Path(file_value.path).stem,
                    source_format="mermaid",
                    rendered_format=None,
                    content_type="text/plain; charset=utf-8",
                    digest=_file_digest(resolved) if resolved is not None else None,
                    updated_at=_file_updated_at(stat) if stat is not None else None,
                )
            )
        for path in sorted(directory.glob("*.svg"), key=lambda item: item.name):
            metadata_path = self._svg_metadata_path(path)
            if metadata_path is None:
                continue
            diagram = self._read_svg_diagram(
                workspace=workspace,
                path=path,
                scope=scope,
                spec_id=spec_id,
                metadata_path=metadata_path,
            )
            if diagram is not None:
                diagrams.append(diagram)
        return tuple(diagrams)

    def _read_svg_diagram(
        self,
        *,
        workspace: Path,
        path: Path,
        scope: str,
        spec_id: str | None,
        metadata_path: Path,
    ) -> SddDiagram | None:
        resolved = _safe_resolve(path)
        metadata_resolved = _safe_resolve(metadata_path)
        if (
            resolved is None
            or metadata_resolved is None
            or not _is_relative_to(resolved, workspace)
            or not _is_relative_to(metadata_resolved, workspace)
            or not _safe_is_file(resolved)
            or not _safe_is_file(metadata_resolved)
        ):
            return None
        if resolved.suffix.lower() not in ALLOWED_RENDERED_DIAGRAM_EXTENSIONS:
            return None
        try:
            metadata = parse_simple_yaml(
                metadata_resolved.read_text(encoding="utf-8", errors="replace")
            )
        except SddStandardError:
            return None
        if not isinstance(metadata, dict):
            return None
        if not _metadata_describes_svg(metadata):
            return None
        stat = resolved.stat()
        rel_path = resolved.relative_to(workspace).as_posix()
        metadata_rel = metadata_resolved.relative_to(workspace).as_posix()
        error: str | None = None
        content: str | None = None
        if stat.st_size > DEFAULT_SDD_SVG_MAX_BYTES:
            error = "file_too_large"
        else:
            content = resolved.read_text(encoding="utf-8", errors="replace")
            if not _is_safe_svg_content(content):
                error = "unsafe_svg"
                content = None
        return SddDiagram(
            path=rel_path,
            title=_optional_metadata_string(metadata, "title")
            or _optional_metadata_string(metadata, "name"),
            size_bytes=stat.st_size,
            content=content,
            diagram_type=_optional_metadata_string(metadata, "diagram_type")
            or "uml-component-svg",
            scope=scope,
            error=error,
            spec_id=spec_id,
            diagram_id=_optional_metadata_string(metadata, "diagram_id")
            or resolved.stem,
            source_format=_optional_metadata_string(metadata, "source_format") or "svg",
            rendered_format=_optional_metadata_string(metadata, "rendered_format")
            or "svg",
            content_type="image/svg+xml; charset=utf-8",
            digest=_file_digest(resolved),
            updated_at=_file_updated_at(stat),
            metadata_path=metadata_rel,
            renderer=_optional_metadata_string(metadata, "renderer"),
        )

    def _svg_metadata_path(self, path: Path) -> Path | None:
        for suffix in (".yaml", ".yml"):
            candidate = path.with_suffix(suffix)
            if _safe_is_file(candidate):
                return candidate
        return None

    def _resolve_rendered_diagram_path(self, workspace: Path, diagram_path: str) -> Path:
        raw_path = diagram_path.strip()
        if not raw_path:
            raise SddProjectError("diagram_path is required.")
        candidate = _safe_resolve(workspace / raw_path)
        if (
            candidate is None
            or not _is_relative_to(candidate, workspace)
            or not _safe_is_file(candidate)
            or candidate.suffix.lower() != ".svg"
        ):
            raise SddProjectError("Rendered diagram not found.")
        metadata_path = self._svg_metadata_path(candidate)
        if metadata_path is None:
            raise SddProjectError("Rendered diagram metadata not found.")
        rel_parts = candidate.relative_to(workspace).parts
        if not _is_allowed_diagram_artifact_location(rel_parts):
            raise SddProjectError("Rendered diagram path is not an SDD diagram artifact.")
        return candidate

    def _read_optional_file(
        self, workspace: Path, relative_path: str
    ) -> SddFile | None:
        path = _safe_resolve(workspace / relative_path)
        if path is None or not _is_relative_to(path, workspace) or not path.is_file():
            return None
        if path.suffix.lower() not in ALLOWED_SDD_EXTENSIONS:
            return None
        stat = path.stat()
        rel_path = path.relative_to(workspace).as_posix()
        if stat.st_size > self._file_max_bytes:
            return SddFile(
                path=rel_path,
                title=None,
                size_bytes=stat.st_size,
                content=None,
                error="file_too_large",
            )
        content = path.read_text(encoding="utf-8", errors="replace")
        return SddFile(
            path=rel_path,
            title=_first_markdown_heading(content),
            size_bytes=stat.st_size,
            content=content,
        )

    def _read_file_metadata(self, workspace: Path, relative_path: str) -> SddFile | None:
        path = _safe_resolve(workspace / relative_path)
        if path is None or not _is_relative_to(path, workspace) or not path.is_file():
            return None
        if path.suffix.lower() not in ALLOWED_SDD_EXTENSIONS:
            return None
        stat = path.stat()
        rel_path = path.relative_to(workspace).as_posix()
        return SddFile(
            path=rel_path,
            title=None,
            size_bytes=stat.st_size,
            content=None,
        )

    def _allowed_file_exists(self, workspace: Path, relative_path: str) -> bool:
        path = _safe_resolve(workspace / relative_path)
        if path is None:
            return False
        return (
            _is_relative_to(path, workspace)
            and path.suffix.lower() in ALLOWED_SDD_EXTENSIONS
            and _safe_is_file(path)
        )

    def _list_allowed_files(
        self,
        workspace: Path,
        relative_dir: str,
        *,
        suffix: str | None = None,
    ) -> tuple[Path, ...]:
        directory = _safe_resolve(workspace / relative_dir)
        if (
            directory is None
            or not _is_relative_to(directory, workspace)
            or not directory.is_dir()
        ):
            return ()
        files: list[Path] = []
        for raw_path in _safe_iterdir(directory):
            path = _safe_resolve(raw_path)
            if path is None:
                continue
            if not _is_relative_to(path, workspace) or not _safe_is_file(path):
                continue
            if suffix is not None and path.suffix.lower() != suffix:
                continue
            if path.suffix.lower() not in ALLOWED_SDD_EXTENSIONS:
                continue
            files.append(path)
        return tuple(files)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _normalize_workspace_alias_key(value: str) -> str:
    raw_value = (value or "").strip().lower()
    if not raw_value:
        return ""
    return "-".join(part for part in re.split(r"[^a-z0-9_.-]+", raw_value) if part)


def _safe_iterdir(path: Path) -> tuple[Path, ...]:
    try:
        return tuple(path.iterdir())
    except OSError:
        return ()


def _safe_resolve(path: Path) -> Path | None:
    try:
        return path.resolve()
    except (OSError, RuntimeError):
        return None


def _is_archived_spec_dir(path: Path) -> bool:
    name = path.name.strip().lower()
    return (
        name in ARCHIVED_SPEC_DIR_NAMES
        or name.startswith("archive-")
        or name.startswith("_archive-")
    )


def _safe_is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


def _string_items(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    items: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            items.append(item.strip())
    return tuple(items)


def _positive_int(value: object, fallback: int) -> int:
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str):
        try:
            parsed = int(value.strip())
        except ValueError:
            return fallback
        return parsed if parsed > 0 else fallback
    return fallback


def _tree_node_id(payload: dict[str, object], fallback: str) -> str:
    raw = _optional_str(payload.get("id"))
    return raw or fallback


def _tree_node_title(
    payload: dict[str, object],
    file_value: SddFile | None,
    fallback: str,
) -> str:
    raw = _optional_str(payload.get("title") or payload.get("name"))
    if raw:
        return raw
    if file_value is not None and file_value.title:
        return file_value.title
    return fallback


def _tree_node_status(payload: dict[str, object]) -> str:
    return _optional_str(payload.get("status")) or "planned"


def _tree_node_description(payload: dict[str, object]) -> str:
    return _optional_str(payload.get("description")) or ""


def _tree_path_label(rel_dir: str, relative_path: str | None, fallback: str) -> str:
    path = (relative_path or "").strip().lstrip("/")
    if not path or ".." in Path(path).parts:
        return fallback
    if path.startswith("specs/"):
        return path
    return f"{rel_dir}/{path}"


def _tree_diagrams(tree: SddSpecTree | None) -> tuple[SddDiagram, ...]:
    if tree is None:
        return ()
    diagrams: list[SddDiagram] = list(tree.diagrams)
    for plan in tree.plans:
        diagrams.extend(plan.diagrams)
        for task in plan.tasks:
            diagrams.extend(task.diagrams)
    return tuple(diagrams)


def _unique_diagrams(diagrams: tuple[SddDiagram, ...]) -> tuple[SddDiagram, ...]:
    unique: list[SddDiagram] = []
    seen: set[str] = set()
    for diagram in diagrams:
        if diagram.path in seen:
            continue
        seen.add(diagram.path)
        unique.append(diagram)
    return tuple(unique)


def _first_markdown_heading(content: str | None) -> str | None:
    if not content:
        return None
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or None
    return None


def _fallback_title(spec_id: str, spec_file: SddFile | None) -> str:
    if spec_file is not None and spec_file.title:
        return spec_file.title
    return spec_id


def _fallback_description(spec_file: SddFile | None) -> str:
    if spec_file is None or not spec_file.content:
        return ""
    in_frontmatter = False
    for line in spec_file.content.splitlines():
        stripped = line.strip()
        if stripped == "---":
            in_frontmatter = not in_frontmatter
            continue
        if in_frontmatter or not stripped or stripped.startswith("#"):
            continue
        if ":" in stripped and len(stripped.split(":", 1)[0].split()) <= 3:
            continue
        return stripped[:240]
    return ""


def _task_summary_from_metadata_or_file(
    metadata: dict[str, object],
    tasks_file: SddFile | None,
) -> SddSpecTaskSummary:
    raw_tasks = metadata.get("tasks")
    if isinstance(raw_tasks, dict):
        total = _safe_int(raw_tasks.get("total"))
        completed = _safe_int(raw_tasks.get("completed"))
        pending = _safe_int(raw_tasks.get("pending"))
        if total is not None and completed is not None and pending is not None:
            return SddSpecTaskSummary(total=total, completed=completed, pending=pending)
    return _task_summary_from_markdown(tasks_file.content if tasks_file else None)


def _task_summary_from_markdown(content: str | None) -> SddSpecTaskSummary:
    if not content:
        return SddSpecTaskSummary(total=0, completed=0, pending=0)
    total = 0
    completed = 0
    for line in content.splitlines():
        stripped = line.strip().lower()
        if stripped.startswith(("- [ ]", "* [ ]")):
            total += 1
        elif stripped.startswith(("- [x]", "* [x]")):
            total += 1
            completed += 1
    return SddSpecTaskSummary(
        total=total,
        completed=completed,
        pending=max(total - completed, 0),
    )


def _generated_metadata(metadata: dict[str, object]) -> SddSpecGeneratedMetadata:
    generated = metadata.get("generated")
    if not isinstance(generated, dict):
        generated = {}
    return SddSpecGeneratedMetadata(
        title=_safe_bool(generated.get("title")),
        description=_safe_bool(generated.get("description")),
        user_pinned_title=_safe_bool(generated.get("user_pinned_title")),
        user_pinned_description=_safe_bool(generated.get("user_pinned_description")),
    )


def _metadata_stale_paths(
    workspace: Path,
    rel_dir: str,
    metadata: dict[str, object],
) -> tuple[str, ...]:
    raw_digests = metadata.get("source_digests")
    if not isinstance(raw_digests, dict):
        return ()
    stale: list[str] = []
    for relative_name, expected_digest in raw_digests.items():
        relative_name_str = str(relative_name)
        if "/" in relative_name_str or "\\" in relative_name_str:
            continue
        if relative_name_str not in {
            "spec.md",
            "plan.md",
            "tasks.md",
            "traceability.yaml",
        }:
            continue
        path = _safe_resolve(workspace / rel_dir / relative_name_str)
        if path is None or not _is_relative_to(path, workspace) or not path.is_file():
            stale.append(relative_name_str)
            continue
        actual_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_digest != str(expected_digest):
            stale.append(relative_name_str)
    return tuple(stale)


def _safe_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _safe_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1"}
    return False


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _diagram_type(content: str | None) -> str:
    if not content or not content.strip():
        return "unknown"
    first_line = content.strip().splitlines()[0].strip().lower()
    if first_line.startswith("sequencediagram"):
        return "sequence"
    if first_line.startswith("flowchart") or first_line.startswith("graph"):
        return "flowchart"
    if first_line.startswith("statediagram"):
        return "state"
    if first_line.startswith("erdiagram"):
        return "erd"
    if first_line.startswith("gantt"):
        return "gantt"
    return "mermaid"


def _metadata_describes_svg(metadata: dict[str, Any]) -> bool:
    source_format = _optional_metadata_string(metadata, "source_format")
    rendered_format = _optional_metadata_string(metadata, "rendered_format")
    source = _optional_metadata_string(metadata, "source")
    renderer = _optional_metadata_string(metadata, "renderer")
    return (
        source_format == "svg"
        or rendered_format == "svg"
        or (source is not None and source.lower().endswith(".svg"))
        or renderer == "diagram-mcp-rendering-engine"
    )


def _optional_metadata_string(metadata: dict[str, Any], key: str) -> str | None:
    value = metadata.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _is_safe_svg_content(content: str) -> bool:
    lowered = content[:4096].lower()
    stripped = content.lstrip()
    if not stripped.startswith("<svg") and "<svg" not in lowered:
        return False
    forbidden = (
        "<script",
        "<foreignobject",
        "javascript:",
        "data:text/html",
        "onload=",
        "onclick=",
        "onerror=",
    )
    return not any(token in content.lower() for token in forbidden)


def _file_digest(path: Path | None) -> str | None:
    if path is None or not _safe_is_file(path):
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _file_updated_at(stat: object) -> str:
    mtime = getattr(stat, "st_mtime", None)
    if not isinstance(mtime, (int, float)):
        return datetime.now(UTC).isoformat()
    return datetime.fromtimestamp(mtime, tz=UTC).isoformat()


def _safe_diagram_id(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip()).strip("-._")
    if not normalized or normalized in {".", ".."}:
        raise SddProjectError("diagram_id must contain a safe filename token.")
    if "/" in normalized or "\\" in normalized:
        raise SddProjectError("diagram_id must not contain path separators.")
    return normalized[:96]


def _is_allowed_diagram_artifact_location(parts: tuple[str, ...]) -> bool:
    if len(parts) >= 2 and parts[0] == "architecture":
        return True
    return len(parts) >= 4 and parts[0] == "specs" and parts[2] == "diagrams"


def _with_primary(
    primary: SddFile | None,
    files: tuple[SddFile, ...],
) -> tuple[SddFile, ...]:
    if primary is None:
        return files
    return (primary, *tuple(file for file in files if file.path != primary.path))
