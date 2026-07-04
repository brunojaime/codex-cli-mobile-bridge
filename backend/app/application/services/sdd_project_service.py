from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


ALLOWED_SDD_EXTENSIONS = frozenset({".md", ".mmd", ".yaml", ".yml", ".json"})
DEFAULT_SDD_FILE_MAX_BYTES = 256_000


class SddProjectError(RuntimeError):
    pass


class SddWorkspacePathError(SddProjectError):
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
    missing: tuple[str, ...]


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
        self._file_max_bytes = file_max_bytes

    def list_projects(self) -> tuple[SddProjectSummary, ...]:
        roots: list[Path] = []
        if self._projects_root.is_dir():
            for child in sorted(self._projects_root.iterdir(), key=lambda item: item.name):
                if child.is_dir():
                    try:
                        roots.append(self._validate_workspace_path(str(child)))
                    except SddWorkspacePathError:
                        continue
        for alias_path in self._workspace_aliases.values():
            if alias_path.is_dir() and alias_path not in roots:
                roots.append(alias_path)
        return tuple(self._project_summary(root) for root in roots)

    def get_project(self, workspace_path: str) -> SddProject:
        return self._project_snapshot(self._validate_workspace_path(workspace_path))

    def get_diagrams(self, workspace_path: str) -> tuple[SddDiagram, ...]:
        project = self.get_project(workspace_path)
        diagrams = list(project.architecture_diagrams)
        for spec in project.specs:
            diagrams.extend(spec.diagrams)
        return tuple(diagrams)

    def _validate_workspace_path(self, workspace_path: str) -> Path:
        raw_path = workspace_path.strip()
        if not raw_path:
            raise SddWorkspacePathError("workspace_path is required.")
        alias_path = self._workspace_aliases.get(raw_path)
        candidate = alias_path if alias_path is not None else Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = self._projects_root / candidate
        resolved = candidate.resolve()
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
        return any(path == alias_path for alias_path in self._workspace_aliases.values())

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
                if (
                    not feature_dir.is_dir()
                    or not _is_relative_to(feature_dir, specs_root)
                    or not _is_relative_to(feature_dir, workspace)
                ):
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

    def _read_specs(self, workspace: Path) -> tuple[SddSpec, ...]:
        specs_root = _safe_resolve(workspace / "specs")
        if (
            specs_root is None
            or not _is_relative_to(specs_root, workspace)
            or not specs_root.is_dir()
        ):
            return ()
        specs: list[SddSpec] = []
        for raw_feature_dir in sorted(
            _safe_iterdir(specs_root),
            key=lambda item: item.name,
        ):
            feature_dir = _safe_resolve(raw_feature_dir)
            if feature_dir is None:
                continue
            if (
                not feature_dir.is_dir()
                or not _is_relative_to(feature_dir, specs_root)
                or not _is_relative_to(feature_dir, workspace)
            ):
                continue
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
            missing = [
                filename
                for filename, file_value in (
                    ("spec.md", spec_file),
                    ("plan.md", plan_file),
                    ("tasks.md", tasks_file),
                )
                if file_value is None
            ]
            specs.append(
                SddSpec(
                    id=feature_dir.name,
                    title=(
                        spec_file.title
                        if spec_file and spec_file.title
                        else feature_dir.name
                    ),
                    path=rel_dir,
                    spec=spec_file,
                    plan=plan_file,
                    tasks=tasks_file,
                    spec_files=spec_files,
                    plan_files=plan_files,
                    task_files=task_files,
                    slice_docs=slice_docs,
                    diagrams=self._read_diagrams(
                        workspace,
                        f"{rel_dir}/diagrams",
                        scope=feature_dir.name,
                    ),
                    missing=tuple(missing),
                )
            )
        return tuple(specs)

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
                if (
                    relative_dir == feature_rel_dir
                    and not path.name.startswith((f"{root_prefix}-", f"{root_prefix}_"))
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
        for path in sorted(directory.glob("*.mmd"), key=lambda item: item.name):
            rel_path = path.relative_to(workspace).as_posix()
            file_value = self._read_optional_file(workspace, rel_path)
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

    def _read_optional_file(self, workspace: Path, relative_path: str) -> SddFile | None:
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


def _safe_is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


def _first_markdown_heading(content: str | None) -> str | None:
    if not content:
        return None
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or None
    return None


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


def _with_primary(
    primary: SddFile | None,
    files: tuple[SddFile, ...],
) -> tuple[SddFile, ...]:
    if primary is None:
        return files
    return (primary, *tuple(file for file in files if file.path != primary.path))
