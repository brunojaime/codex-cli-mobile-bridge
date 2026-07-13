from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_STANDARD_ID = "workbench-sdd/v1"
CANONICAL_STANDARD_ID = DEFAULT_STANDARD_ID
CANONICAL_STANDARD_ARTIFACT = (
    "backend/app/infrastructure/config/sdd_standards/workbench-sdd/v1.yaml"
)
SUPPORTED_STANDARD_FAMILY = "workbench-sdd"
SUPPORTED_STANDARD_MAJOR = "v1"
LLM_RESOLUTION_TEMPLATE_NAME = "llm-resolution.md"

_DEFAULT_LLM_RESOLUTION_TEMPLATE = """Workbench SDD standard resolution:
- Requested standard: {requested_id}
- Canonical standard: {canonical_id}
- Canonical in-repo artifact: {canonical_artifact}
- Loaded artifact: {loaded_artifact}
- Version semantics: {version_semantics}
- LLM rule: use the backend-provided serialized standard payload or the canonical artifact above; do not infer a divergent standard from project files.
"""


class SddStandardError(RuntimeError):
    pass


class SddUnknownStandardError(SddStandardError):
    pass


class SddInvalidStandardError(SddStandardError):
    pass


@dataclass(frozen=True, slots=True)
class SddStandard:
    id: str
    version: int
    source_path: Path
    payload: dict[str, Any]
    requested_id: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "canonical_id": self.id,
            "requested_id": self.requested_id,
            "version": self.version,
            "source_path": str(self.source_path),
            "payload": self.payload,
        }


class SddStandardService:
    def __init__(self, standards_root: str | Path | None = None) -> None:
        self._standards_root = (
            Path(standards_root).expanduser().resolve()
            if standards_root is not None
            else _default_standards_root()
        )

    @property
    def standards_root(self) -> Path:
        return self._standards_root

    def load(self, standard_id: str = DEFAULT_STANDARD_ID) -> SddStandard:
        standard_id = standard_id.strip()
        if not standard_id:
            raise SddUnknownStandardError("sdd.standard is required for write flows.")
        canonical_id, source_path = self._resolve_standard(standard_id)
        if not source_path.is_file():
            raise SddUnknownStandardError(
                f"Unknown SDD standard '{standard_id}'. Expected canonical "
                f"artifact for {canonical_id} at "
                f"{source_path}."
            )
        payload = parse_simple_yaml(source_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise SddInvalidStandardError(f"{source_path} must contain a mapping.")
        self._validate_payload(
            payload,
            source_path=source_path,
            canonical_id=canonical_id,
            requested_id=standard_id,
        )
        return SddStandard(
            id=str(payload["id"]),
            version=int(payload["version"]),
            source_path=source_path,
            payload=payload,
            requested_id=standard_id,
        )

    def llm_resolution_instructions(
        self,
        standard_id: str = DEFAULT_STANDARD_ID,
    ) -> str:
        standard = self.load(standard_id)
        template_path = self._llm_resolution_template_path()
        template = (
            template_path.read_text(encoding="utf-8")
            if template_path.is_file()
            else _DEFAULT_LLM_RESOLUTION_TEMPLATE
        )
        return template.format(
            requested_id=standard.requested_id,
            canonical_id=standard.id,
            canonical_artifact=CANONICAL_STANDARD_ARTIFACT,
            loaded_artifact=standard.source_path,
            version_semantics=(
                "workbench-sdd/v1 is supported; workbench-sdd/v1.x aliases "
                "are backward-compatible and resolve to the canonical v1 "
                "artifact; unknown families or major versions are hard errors "
                "for write, context, indexing, scaffold, and Codex action flows"
            ),
        ).strip()

    def _llm_resolution_template_path(self) -> Path:
        return (
            self._standards_root
            / SUPPORTED_STANDARD_FAMILY
            / LLM_RESOLUTION_TEMPLATE_NAME
        )

    def _resolve_standard(self, standard_id: str) -> tuple[str, Path]:
        family, separator, version = standard_id.partition("/")
        if not separator or not family or not version:
            raise SddUnknownStandardError(
                f"Unsupported SDD standard '{standard_id}'. Use "
                f"'{CANONICAL_STANDARD_ID}' or '{SUPPORTED_STANDARD_FAMILY}/v1.x'."
            )
        if family != SUPPORTED_STANDARD_FAMILY:
            raise SddUnknownStandardError(
                f"Unknown SDD standard family '{family}' in '{standard_id}'. "
                f"Supported family is '{SUPPORTED_STANDARD_FAMILY}'."
            )
        if not _is_supported_v1_version(version):
            raise SddUnknownStandardError(
                f"Unsupported SDD standard version '{standard_id}'. Supported "
                f"versions are '{CANONICAL_STANDARD_ID}' and backward-compatible "
                f"'{SUPPORTED_STANDARD_FAMILY}/v1.x' aliases."
            )
        return CANONICAL_STANDARD_ID, (
            self._standards_root / SUPPORTED_STANDARD_FAMILY / "v1.yaml"
        ).resolve()

    def _validate_payload(
        self,
        payload: dict[str, Any],
        *,
        source_path: Path,
        canonical_id: str,
        requested_id: str,
    ) -> None:
        if payload.get("kind") != "codex.workbenchSddStandard":
            raise SddInvalidStandardError(
                f"{source_path} has invalid kind {payload.get('kind')!r}."
            )
        if payload.get("id") != canonical_id:
            raise SddInvalidStandardError(
                f"{source_path} id {payload.get('id')!r} does not match "
                f"{canonical_id!r}."
            )
        version = payload.get("version")
        if not isinstance(version, int):
            raise SddInvalidStandardError(f"{source_path} version must be an integer.")
        supported_ids = _list_at(payload, "compatibility", "supported_ids")
        if canonical_id not in supported_ids:
            raise SddInvalidStandardError(
                f"{source_path} compatibility.supported_ids must include "
                f"{canonical_id} for requested {requested_id}."
            )
        required_safety_rules = _list_at(
            payload,
            "context_rules",
            "required_safety_rules",
        )
        for expected_rule in (
            "manifest_first_resolution",
            "baseline_impact_gates",
            "no_broad_read",
            "unknown_version_hard_failure",
        ):
            if expected_rule not in required_safety_rules:
                raise SddInvalidStandardError(
                    f"{source_path} is missing required safety rule {expected_rule}."
                )


def parse_simple_yaml(text: str) -> Any:
    lines = [
        (len(raw_line) - len(raw_line.lstrip(" ")), _strip_comment(raw_line).strip())
        for raw_line in text.splitlines()
        if _strip_comment(raw_line).strip()
    ]
    if not lines:
        return {}
    value, index = _parse_block(lines, 0, lines[0][0])
    if index != len(lines):
        raise SddInvalidStandardError("Unexpected trailing YAML content.")
    return value


def _parse_block(
    lines: list[tuple[int, str]],
    index: int,
    indent: int,
) -> tuple[Any, int]:
    if index >= len(lines):
        return {}, index
    current_indent, stripped = lines[index]
    if current_indent < indent:
        return {}, index
    if current_indent != indent:
        raise SddInvalidStandardError("Invalid YAML indentation.")
    if _is_supported_scalar(stripped):
        return _parse_scalar(stripped), index + 1
    if stripped.startswith("- "):
        return _parse_list(lines, index, indent)
    return _parse_mapping(lines, index, indent)


def _parse_mapping(
    lines: list[tuple[int, str]],
    index: int,
    indent: int,
) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    while index < len(lines):
        current_indent, stripped = lines[index]
        if current_indent < indent:
            break
        if current_indent != indent:
            raise SddInvalidStandardError("Invalid YAML mapping indentation.")
        if stripped.startswith("- "):
            break
        key, separator, raw_value = stripped.partition(":")
        if not separator:
            raise SddInvalidStandardError(f"Invalid YAML mapping line: {stripped}")
        key = key.strip()
        raw_value = raw_value.strip()
        index += 1
        if raw_value:
            result[key] = _parse_scalar(raw_value)
            continue
        if index < len(lines) and lines[index][0] > current_indent:
            result[key], index = _parse_block(lines, index, lines[index][0])
        else:
            result[key] = {}
    return result, index


def _parse_list(
    lines: list[tuple[int, str]],
    index: int,
    indent: int,
) -> tuple[list[Any], int]:
    result: list[Any] = []
    while index < len(lines):
        current_indent, stripped = lines[index]
        if current_indent < indent:
            break
        if current_indent != indent or not stripped.startswith("- "):
            break
        raw_value = stripped[2:].strip()
        index += 1
        if raw_value:
            result.append(_parse_scalar(raw_value))
            continue
        if index < len(lines) and lines[index][0] > current_indent:
            value, index = _parse_block(lines, index, lines[index][0])
            result.append(value)
        else:
            result.append(None)
    return result, index


def _parse_scalar(raw_value: str) -> object:
    if raw_value.startswith("[") and raw_value.endswith("]"):
        inner = raw_value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(item.strip()) for item in _split_inline_list(inner)]
    if raw_value in {"true", "True"}:
        return True
    if raw_value in {"false", "False"}:
        return False
    if raw_value in {"null", "Null", "~"}:
        return None
    if (raw_value.startswith('"') and raw_value.endswith('"')) or (
        raw_value.startswith("'") and raw_value.endswith("'")
    ):
        return raw_value[1:-1]
    try:
        return int(raw_value)
    except ValueError:
        return raw_value


def _is_supported_scalar(raw_value: str) -> bool:
    if raw_value.startswith("[") and raw_value.endswith("]"):
        return True
    return raw_value in {"true", "True", "false", "False", "null", "Null", "~"}


def _strip_comment(raw_line: str) -> str:
    in_single = False
    in_double = False
    for index, char in enumerate(raw_line):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            return raw_line[:index]
    return raw_line


def _split_inline_list(raw_value: str) -> list[str]:
    result: list[str] = []
    current: list[str] = []
    in_single = False
    in_double = False
    for char in raw_value:
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        if char == "," and not in_single and not in_double:
            result.append("".join(current))
            current = []
            continue
        current.append(char)
    result.append("".join(current))
    return result


def _default_standards_root() -> Path:
    return (
        Path(__file__).resolve().parents[4]
        / "backend"
        / "app"
        / "infrastructure"
        / "config"
        / "sdd_standards"
    )


def _list_at(payload: dict[str, Any], *path: str) -> list[str]:
    value: Any = payload
    for key in path:
        if not isinstance(value, dict):
            raise SddInvalidStandardError("Expected list at " + ".".join(path))
        value = value.get(key)
    if not _is_string_list(value):
        raise SddInvalidStandardError("Expected string list at " + ".".join(path))
    return value


def _is_string_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _is_supported_v1_version(version: str) -> bool:
    if version == SUPPORTED_STANDARD_MAJOR:
        return True
    prefix = SUPPORTED_STANDARD_MAJOR + "."
    if not version.startswith(prefix):
        return False
    suffix = version[len(prefix) :]
    return bool(suffix) and all(part.isdigit() for part in suffix.split("."))
