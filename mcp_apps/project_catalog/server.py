from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations


_KNOWN_EXTENSION_LANGUAGES = {
    ".c": "C",
    ".cc": "C++",
    ".cpp": "C++",
    ".cs": "C#",
    ".css": "CSS",
    ".dart": "Dart",
    ".go": "Go",
    ".h": "C/C++ Header",
    ".hpp": "C++ Header",
    ".html": "HTML",
    ".java": "Java",
    ".js": "JavaScript",
    ".json": "JSON",
    ".jsx": "React",
    ".kt": "Kotlin",
    ".md": "Markdown",
    ".mjs": "JavaScript",
    ".php": "PHP",
    ".py": "Python",
    ".rb": "Ruby",
    ".rs": "Rust",
    ".scss": "SCSS",
    ".sh": "Shell",
    ".sql": "SQL",
    ".swift": "Swift",
    ".toml": "TOML",
    ".ts": "TypeScript",
    ".tsx": "React",
    ".yaml": "YAML",
    ".yml": "YAML",
}

_SIGNATURE_FILES = (
    "pyproject.toml",
    "package.json",
    "pubspec.yaml",
    "Cargo.toml",
    "go.mod",
    "Dockerfile",
    "README.md",
    "README.rst",
)

_IGNORE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    ".dart_tool",
    ".idea",
    ".vscode",
    "__pycache__",
}

_MAX_SCAN_FILES = 300
_README_PREVIEW_CHARS = 320

_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


@dataclass(slots=True)
class ProjectMetadata:
    name: str
    path: str
    last_modified_at: str | None
    has_git: bool
    top_level_entry_count: int
    file_sample_count: int
    detected_languages: list[str]
    signature_files: list[str]
    readme_path: str | None
    readme_excerpt: str | None


mcp = FastMCP(
    "Project Catalog",
    instructions=(
        "Expose local repository folders from PROJECTS_ROOT in a read-only way. "
        "Use these tools to understand which projects exist before asking the user "
        "to choose a workspace or before planning repo-specific work."
    ),
    json_response=True,
    log_level="WARNING",
)


def _projects_root() -> Path:
    configured = os.environ.get("PROJECTS_ROOT", "").strip()
    return Path(configured or ".").expanduser().resolve()


def _iter_projects() -> list[Path]:
    root = _projects_root()
    if not root.exists():
        return []
    return [
        path
        for path in sorted(root.iterdir())
        if path.is_dir() and not path.name.startswith(".")
    ]


def _collect_project_metadata(
    project_dir: Path,
    *,
    include_readme_excerpt: bool,
) -> ProjectMetadata:
    counter: Counter[str] = Counter()
    scanned_files = 0
    signature_files: list[str] = []

    for candidate in _SIGNATURE_FILES:
        if (project_dir / candidate).exists():
            signature_files.append(candidate)

    for path in project_dir.rglob("*"):
        if scanned_files >= _MAX_SCAN_FILES:
            break
        if path.is_dir():
            if path.name in _IGNORE_DIRS:
                continue
            continue
        if any(part in _IGNORE_DIRS for part in path.parts):
            continue
        scanned_files += 1
        language = _KNOWN_EXTENSION_LANGUAGES.get(path.suffix.lower())
        if language is not None:
            counter[language] += 1

    readme_path = _resolve_readme(project_dir)
    return ProjectMetadata(
        name=project_dir.name,
        path=str(project_dir),
        last_modified_at=_isoformat(project_dir.stat().st_mtime),
        has_git=(project_dir / ".git").exists(),
        top_level_entry_count=_top_level_entry_count(project_dir),
        file_sample_count=scanned_files,
        detected_languages=[
            language
            for language, _count in counter.most_common(5)
        ],
        signature_files=signature_files,
        readme_path=str(readme_path) if readme_path is not None else None,
        readme_excerpt=_read_readme_excerpt(readme_path) if include_readme_excerpt else None,
    )


def _resolve_readme(project_dir: Path) -> Path | None:
    for candidate in ("README.md", "README.rst", "README.txt", "readme.md"):
        path = project_dir / candidate
        if path.exists():
            return path
    return None


def _read_readme_excerpt(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    if not text:
        return None
    excerpt = " ".join(text.split())
    return excerpt[:_README_PREVIEW_CHARS]


def _isoformat(timestamp: float) -> str | None:
    try:
        return datetime.fromtimestamp(timestamp, tz=UTC).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _top_level_entry_count(project_dir: Path) -> int:
    try:
        return sum(1 for _ in project_dir.iterdir())
    except OSError:
        return 0


def _list_projects_payload(
    *,
    limit: int,
    include_readme_excerpt: bool,
) -> dict[str, Any]:
    projects = _iter_projects()[: max(limit, 0)]
    metadata = [
        asdict(
            _collect_project_metadata(
                project_dir,
                include_readme_excerpt=include_readme_excerpt,
            )
        )
        for project_dir in projects
    ]
    return {
        "projects_root": str(_projects_root()),
        "project_count": len(_iter_projects()),
        "projects": metadata,
    }


def _project_payload(
    *,
    project_name: str,
    include_readme_excerpt: bool,
) -> dict[str, Any]:
    for project_dir in _iter_projects():
        if project_dir.name == project_name:
            return {
                "project": asdict(
                    _collect_project_metadata(
                        project_dir,
                        include_readme_excerpt=include_readme_excerpt,
                    )
                )
            }
    raise ValueError(
        f"Project `{project_name}` was not found under `{_projects_root()}`."
    )


@mcp.tool(
    title="List Projects",
    description=(
        "List local projects under PROJECTS_ROOT together with safe, read-only metadata "
        "such as detected languages, signature files, README presence, and timestamps."
    ),
    annotations=_ANNOTATIONS,
)
def list_projects(
    limit: int = 25,
    include_readme_excerpt: bool = False,
) -> dict[str, Any]:
    return _list_projects_payload(
        limit=limit,
        include_readme_excerpt=include_readme_excerpt,
    )


@mcp.tool(
    title="Get Project Metadata",
    description=(
        "Inspect one project from PROJECTS_ROOT and return metadata useful for selecting "
        "or understanding that workspace before coding."
    ),
    annotations=_ANNOTATIONS,
)
def get_project_metadata(
    project_name: str,
    include_readme_excerpt: bool = True,
) -> dict[str, Any]:
    return _project_payload(
        project_name=project_name,
        include_readme_excerpt=include_readme_excerpt,
    )


@mcp.resource(
    "projects://catalog",
    name="Project Catalog JSON",
    description="Static JSON snapshot of the current project catalog.",
    mime_type="application/json",
)
def projects_catalog_resource() -> str:
    return json.dumps(
        _list_projects_payload(limit=100, include_readme_excerpt=False),
        indent=2,
        sort_keys=True,
    )


@mcp.prompt(
    name="summarize-projects",
    title="Summarize Available Projects",
    description="Ask the model to summarize the currently available local projects.",
)
def summarize_projects_prompt() -> str:
    return (
        "Use the `list_projects` tool first, then summarize the available local projects. "
        "Highlight likely stacks, the presence of README files, and which project looks "
        "most relevant to the current user request."
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
