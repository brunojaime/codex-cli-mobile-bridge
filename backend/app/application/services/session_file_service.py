"""Read-only access to documents in the workspace belonging to a chat."""

from __future__ import annotations

import mimetypes
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_TEXT_BYTES = 256 * 1024
TEXT_EXTENSIONS = frozenset(
    {
        ".md",
        ".markdown",
        ".txt",
        ".json",
        ".csv",
        ".yaml",
        ".yml",
        ".py",
        ".dart",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".css",
        ".html",
        ".htm",
        ".sql",
        ".xml",
        ".svg",
        ".toml",
        ".sh",
        ".mjs",
        ".cjs",
    }
)
IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp"})
FILE_EXTENSIONS = (
    TEXT_EXTENSIONS
    | IMAGE_EXTENSIONS
    | {
        ".pdf",
        ".docx",
        ".xlsx",
        ".pptx",
        ".zip",
    }
)
PRIVATE_PARTS = frozenset(
    {
        ".git",
        ".ssh",
        ".aws",
        ".wrangler",
        ".gnupg",
        ".data",
        ".run",
        ".release-signing",
        "secrets",
        "credentials",
        "node_modules",
        ".venv",
        "key.properties",
        "credentials.json",
        "auth.json",
        "service-account.json",
    }
)


class SessionFileError(ValueError):
    def __init__(self, detail: str, status_code: int = 403) -> None:
        super().__init__(detail)
        self.status_code = status_code


def _private(path: Path) -> bool:
    return any(
        part.lower() in PRIVATE_PARTS or part.lower().startswith(".env")
        for part in path.parts
    )


def _target_path(target: str) -> str:
    target = target.strip()
    if not target or "\x00" in target:
        raise SessionFileError("La referencia al archivo no es válida.", 422)
    target = re.sub(r":\d+(?::\d+)?$", "", target)
    uri = urlsplit(target)
    if uri.scheme and (uri.scheme != "file" or uri.netloc not in {"", "localhost"}):
        raise SessionFileError("Esta referencia no es un archivo del proyecto.", 422)
    path = unquote(uri.path)
    # References from agent replies often end in :line, :line:column or #Lline.
    return re.sub(r":\d+(?::\d+)?$", "", path)


def resolve_session_file(
    workspace: str, target: str, relative_to: str | None = None
) -> Path:
    root = Path(workspace).resolve()
    base = root
    if relative_to:
        parent = resolve_session_file(workspace, relative_to)
        base = parent if parent.is_dir() else parent.parent
    candidate = Path(_target_path(target))
    if not candidate.is_absolute():
        candidate = base / candidate
    # Check both the named path and the symlink destination.
    try:
        named = candidate.relative_to(root)
        path = candidate.resolve()
        resolved = path.relative_to(root)
    except (ValueError, OSError, RuntimeError) as exc:
        raise SessionFileError(
            "El archivo está fuera del proyecto de este chat."
        ) from exc
    if _private(named) or _private(resolved):
        raise SessionFileError("Este archivo privado no se comparte desde el visor.")
    if not path.exists():
        raise SessionFileError("El archivo ya no está disponible en el servidor.", 404)
    if not path.is_dir():
        if not path.is_file() or path.suffix.lower() not in FILE_EXTENSIONS:
            raise SessionFileError(
                "Este tipo de archivo no está disponible en el visor.", 415
            )
        if path.stat().st_size > MAX_FILE_BYTES:
            raise SessionFileError("El archivo supera el límite de 50 MB.", 413)
    return path


def session_file_metadata(
    workspace: str, target: str, relative_to: str | None = None
) -> dict:
    path = resolve_session_file(workspace, target, relative_to)
    root = Path(workspace).resolve()
    kind = (
        "directory"
        if path.is_dir()
        else "image"
        if path.suffix.lower() in IMAGE_EXTENSIONS
        else "text"
        if path.suffix.lower() in TEXT_EXTENSIONS
        else "file"
    )
    result = {
        "name": path.name,
        "path": path.relative_to(root).as_posix(),
        "kind": kind,
        "content_type": mimetypes.guess_type(path.name)[0]
        or "application/octet-stream",
        "size_bytes": 0 if path.is_dir() else path.stat().st_size,
        "text": None,
        "truncated": False,
        "entries": [],
    }
    if kind == "text":
        with path.open("rb") as handle:
            data = handle.read(MAX_TEXT_BYTES + 1)
        result["text"] = data[:MAX_TEXT_BYTES].decode("utf-8", errors="replace")
        result["truncated"] = len(data) > MAX_TEXT_BYTES
    if kind == "directory":
        entries = []
        for child in sorted(path.iterdir(), key=lambda p: p.name.lower()):
            try:
                safe = resolve_session_file(workspace, str(child))
            except SessionFileError:
                continue
            entries.append(
                {
                    "name": child.name,
                    "path": safe.relative_to(root).as_posix(),
                    "is_directory": safe.is_dir(),
                }
            )
            if len(entries) == 200:
                result["truncated"] = True
                break
        result["entries"] = entries
    return result
