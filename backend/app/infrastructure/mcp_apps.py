from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shlex
import subprocess
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


_MCP_APPS_DIR_NAME = "mcp_apps"
_SUPPORTED_TRANSPORTS = {"stdio"}
_MCP_APP_STEP_TIMEOUT_SECONDS = 2.0
_MCP_APP_TOTAL_INSPECTION_TIMEOUT_SECONDS = 8.0
_MCP_GET_SERVER_TIMEOUT_SECONDS = 10.0
_MCP_REMOVE_SERVER_TIMEOUT_SECONDS = 10.0
_MCP_ADD_SERVER_TIMEOUT_SECONDS = 20.0


class _TemplateResolutionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CodexMcpAppPreviewConfig:
    tool_name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class CodexMcpAppSpec:
    app_id: str
    name: str
    description: str
    recommended_server_id: str
    transport: str
    command: str
    args: tuple[str, ...]
    env: tuple[tuple[str, str], ...]
    tags: tuple[str, ...]
    supports_ui_extension: bool
    ui_entry_uri: str | None
    spec_path: str
    preview: CodexMcpAppPreviewConfig | None = None


@dataclass(frozen=True, slots=True)
class CodexMcpAppTool:
    name: str
    title: str | None
    description: str | None
    read_only: bool
    destructive: bool
    idempotent: bool
    open_world: bool
    input_schema: dict[str, Any]


@dataclass(frozen=True, slots=True)
class CodexMcpAppResource:
    name: str
    title: str | None
    uri: str
    description: str | None
    mime_type: str | None


@dataclass(frozen=True, slots=True)
class CodexMcpAppPromptArgument:
    name: str
    description: str | None
    required: bool


@dataclass(frozen=True, slots=True)
class CodexMcpAppPrompt:
    name: str
    title: str | None
    description: str | None
    arguments: tuple[CodexMcpAppPromptArgument, ...]


@dataclass(frozen=True, slots=True)
class CodexMcpAppPreview:
    tool_name: str
    arguments: dict[str, Any]
    result: Any | None
    is_error: bool
    error: str | None = None


@dataclass(frozen=True, slots=True)
class CodexMcpApp:
    app_id: str
    name: str
    description: str
    recommended_server_id: str
    transport: str
    command: str
    args: tuple[str, ...]
    env: tuple[tuple[str, str], ...]
    tags: tuple[str, ...]
    supports_ui_extension: bool
    ui_entry_uri: str | None
    spec_path: str
    installed: bool
    install_state: str
    server_present: bool
    server_presence_known: bool
    config_matches: bool | None
    tools: tuple[CodexMcpAppTool, ...]
    resources: tuple[CodexMcpAppResource, ...]
    prompts: tuple[CodexMcpAppPrompt, ...]
    preview: CodexMcpAppPreview | None = None
    drift_summary: str | None = None
    disabled_reason: str | None = None
    lookup_error: str | None = None
    validation_error: str | None = None
    protocol_error: str | None = None


@dataclass(frozen=True, slots=True)
class CodexMcpAppInstallResult:
    app_id: str
    server_id: str
    already_installed: bool
    reconciled: bool
    command: str
    summary: str


@dataclass(frozen=True, slots=True)
class _CodexMcpAppDiscovery:
    valid_specs: tuple[CodexMcpAppSpec, ...]
    invalid_apps: tuple[CodexMcpApp, ...]


@dataclass(frozen=True, slots=True)
class CodexInstalledMcpServerConfig:
    server_id: str
    enabled: bool
    disabled_reason: str | None
    transport: str
    transport_payload: dict[str, Any]
    command: str | None = None
    args: tuple[str, ...] | None = None
    env: tuple[tuple[str, str], ...] | None = None


@dataclass(frozen=True, slots=True)
class CodexInstalledMcpServerLookup:
    status: str
    server_present: bool
    server_presence_known: bool
    config: CodexInstalledMcpServerConfig | None = None
    error: str | None = None


def discover_repo_mcp_apps(
    *,
    repo_root: Path | None,
    projects_root: str,
) -> list[CodexMcpAppSpec]:
    discovery = _discover_repo_mcp_apps(
        repo_root=repo_root,
        projects_root=projects_root,
    )
    return list(discovery.valid_specs)


def inspect_repo_mcp_apps(
    *,
    command: str,
    repo_root: Path | None,
    projects_root: str,
) -> list[CodexMcpApp]:
    discovery = _discover_repo_mcp_apps(
        repo_root=repo_root,
        projects_root=projects_root,
    )
    inspected_apps = [
        _inspect_app(
            app,
            installed_lookup=get_installed_mcp_server_lookup(
                command,
                app.recommended_server_id,
            ),
        )
        for app in discovery.valid_specs
    ]
    return sorted(
        [*inspected_apps, *discovery.invalid_apps],
        key=lambda app: (app.name.lower(), app.app_id, app.spec_path),
    )


def install_repo_mcp_app(
    command: str,
    *,
    repo_root: Path | None,
    projects_root: str,
    app_id: str,
) -> CodexMcpAppInstallResult:
    app = _require_installable_app(
        requested_app_id=app_id,
        repo_root=repo_root,
        projects_root=projects_root,
    )
    inspected = _inspect_app(app, installed_config=None)
    if inspected.protocol_error is not None:
        raise RuntimeError(
            f"MCP app `{app_id}` failed protocol inspection and is not installable yet. "
            f"{inspected.protocol_error}"
        )
    installed_lookup = get_installed_mcp_server_lookup(
        command, app.recommended_server_id
    )
    if installed_lookup.status == "unreadable":
        raise RuntimeError(
            "Cannot determine the existing Codex server state for "
            f"`{app.recommended_server_id}` safely. {installed_lookup.error} "
            "Install/reconcile was aborted and the stored config was left unchanged."
        )
    installed_config = installed_lookup.config
    reconciled = False
    if installed_config is not None:
        drift_summary = _diff_installed_config(app, installed_config)
        if drift_summary is None and installed_config.enabled:
            return CodexMcpAppInstallResult(
                app_id=app.app_id,
                server_id=app.recommended_server_id,
                already_installed=True,
                reconciled=False,
                command=_format_command_preview(app.command, app.args),
                summary=(
                    f"MCP app `{app.name}` already matches the desired Codex server "
                    f"configuration `{app.recommended_server_id}`."
                ),
            )
        restore_error = _restore_capability_error(installed_config)
        if restore_error is not None:
            disabled_detail = _disabled_reason_detail(installed_config.disabled_reason)
            raise RuntimeError(
                "Cannot automatically reconcile MCP app "
                f"`{app.app_id}` because {restore_error} "
                f"{disabled_detail}"
                "The existing stored Codex server config was left unchanged."
            )
        try:
            _remove_server(command, app.recommended_server_id)
        except RuntimeError as exc:
            raise RuntimeError(
                "Failed to reconcile MCP app "
                f"`{app.app_id}` because removing the existing stored Codex "
                f"server config failed. {exc} Reconcile was aborted before "
                "modifying the stored config."
            ) from exc
        reconciled = True
        try:
            _add_stdio_server(
                command,
                server_id=app.recommended_server_id,
                launch_command=app.command,
                launch_args=app.args,
                launch_env=app.env,
            )
        except RuntimeError as exc:
            rollback_error = _rollback_previous_server_config(command, installed_config)
            if rollback_error is None:
                raise RuntimeError(
                    "Failed to reconcile MCP app "
                    f"`{app.app_id}` because installing the desired config failed. "
                    f"{exc} The previous server config was restored."
                ) from exc
            raise RuntimeError(
                "Failed to reconcile MCP app "
                f"`{app.app_id}` because installing the desired config failed. "
                f"{exc} Rollback also failed: {rollback_error}"
            ) from exc
    else:
        _add_stdio_server(
            command,
            server_id=app.recommended_server_id,
            launch_command=app.command,
            launch_args=app.args,
            launch_env=app.env,
        )

    return CodexMcpAppInstallResult(
        app_id=app.app_id,
        server_id=app.recommended_server_id,
        already_installed=False,
        reconciled=reconciled,
        command=_format_command_preview(app.command, app.args),
        summary=(
            f"Re-enabled MCP app `{app.name}` as `{app.recommended_server_id}`."
            if reconciled
            and installed_config is not None
            and drift_summary is None
            and not installed_config.enabled
            else (
                f"Reconciled MCP app `{app.name}` as `{app.recommended_server_id}`."
                if reconciled
                else f"Installed MCP app `{app.name}` as `{app.recommended_server_id}`."
            )
        ),
    )


def _repo_mcp_apps_root(repo_root: Path | None) -> Path | None:
    if repo_root is None:
        return None
    return repo_root / _MCP_APPS_DIR_NAME


def _discover_repo_mcp_apps(
    *,
    repo_root: Path | None,
    projects_root: str,
) -> _CodexMcpAppDiscovery:
    apps_root = _repo_mcp_apps_root(repo_root)
    if apps_root is None or not apps_root.exists():
        return _CodexMcpAppDiscovery(valid_specs=(), invalid_apps=())

    valid_specs: list[CodexMcpAppSpec] = []
    invalid_apps: list[CodexMcpApp] = []
    for spec_path in sorted(apps_root.glob("*/app.json")):
        spec, invalid_app = _load_app_spec_result(
            spec_path,
            repo_root=repo_root,
            projects_root=projects_root,
        )
        if spec is not None:
            valid_specs.append(spec)
        if invalid_app is not None:
            invalid_apps.append(invalid_app)

    collisions_by_app_id = _find_duplicate_values(
        valid_specs,
        value_getter=lambda app: app.app_id,
    )
    collisions_by_server_id = _find_duplicate_values(
        valid_specs,
        value_getter=lambda app: app.recommended_server_id,
    )

    if collisions_by_app_id or collisions_by_server_id:
        unique_invalid_specs: dict[str, CodexMcpAppSpec] = {}
        for duplicate_value, specs in collisions_by_app_id.items():
            spec_paths = ", ".join(spec.spec_path for spec in specs)
            message = f"Duplicate app_id `{duplicate_value}` declared by {spec_paths}."
            for spec in specs:
                unique_invalid_specs[spec.spec_path] = spec
                invalid_apps.append(
                    _invalid_app_from_spec(
                        spec,
                        validation_error=message,
                    )
                )
        for duplicate_value, specs in collisions_by_server_id.items():
            spec_paths = ", ".join(spec.spec_path for spec in specs)
            message = (
                "Duplicate recommended_server_id "
                f"`{duplicate_value}` declared by {spec_paths}."
            )
            for spec in specs:
                unique_invalid_specs[spec.spec_path] = spec
                invalid_apps.append(
                    _invalid_app_from_spec(
                        spec,
                        validation_error=message,
                    )
                )
        valid_specs = [
            spec for spec in valid_specs if spec.spec_path not in unique_invalid_specs
        ]

    deduped_invalid_apps: dict[tuple[str, str, str], CodexMcpApp] = {}
    for app in invalid_apps:
        deduped_invalid_apps[
            (
                app.app_id,
                app.spec_path,
                app.validation_error or app.protocol_error or "",
            )
        ] = app

    return _CodexMcpAppDiscovery(
        valid_specs=tuple(valid_specs),
        invalid_apps=tuple(deduped_invalid_apps.values()),
    )


def _load_app_spec_result(
    spec_path: Path,
    *,
    repo_root: Path | None,
    projects_root: str,
) -> tuple[CodexMcpAppSpec | None, CodexMcpApp | None]:
    default_app_id = spec_path.parent.name.replace("_", "-")
    default_name = spec_path.parent.name.replace("_", " ").title()
    try:
        payload = json.loads(spec_path.read_text(encoding="utf-8"))
    except OSError as exc:
        return None, _invalid_app_from_path(
            spec_path,
            app_id=default_app_id,
            name=default_name,
            validation_error=f"Failed to read app spec. {exc}",
        )
    except json.JSONDecodeError as exc:
        return None, _invalid_app_from_path(
            spec_path,
            app_id=default_app_id,
            name=default_name,
            validation_error=f"Malformed app.json. {exc}",
        )
    if not isinstance(payload, dict):
        return None, _invalid_app_from_path(
            spec_path,
            app_id=default_app_id,
            name=default_name,
            validation_error="Malformed app.json. Expected a JSON object.",
        )

    args_payload = payload.get("args")
    env_payload = payload.get("env")
    tags_payload = payload.get("tags")
    preview_payload = payload.get("preview_tool")

    app_id = _app_field_value(
        payload,
        field_name="app_id",
        default_value=default_app_id,
    )
    name = _app_field_value(
        payload,
        field_name="name",
        default_value=default_name,
    )
    description = _app_field_value(
        payload,
        field_name="description",
        default_value="",
    )
    recommended_server_id = _app_field_value(
        payload,
        field_name="recommended_server_id",
        default_value=default_app_id,
    )
    transport = _app_field_value(
        payload,
        field_name="transport",
        default_value="stdio",
    )

    if not isinstance(args_payload, list):
        return None, _invalid_app_from_path(
            spec_path,
            app_id=app_id,
            name=name,
            recommended_server_id=recommended_server_id,
            transport=transport,
            validation_error="Invalid app spec: `args` must be a JSON array.",
        )
    if not isinstance(env_payload, dict):
        return None, _invalid_app_from_path(
            spec_path,
            app_id=app_id,
            name=name,
            recommended_server_id=recommended_server_id,
            transport=transport,
            validation_error="Invalid app spec: `env` must be a JSON object.",
        )
    if transport not in _SUPPORTED_TRANSPORTS:
        supported = ", ".join(sorted(_SUPPORTED_TRANSPORTS))
        return None, _invalid_app_from_path(
            spec_path,
            app_id=app_id,
            name=name,
            recommended_server_id=recommended_server_id,
            transport=transport,
            validation_error=(
                f"Unsupported transport `{transport}`. "
                f"This repo currently supports only {supported} MCP apps."
            ),
        )

    raw_command = payload.get("command")
    command_text = _as_optional_str(raw_command)
    if raw_command is None or command_text is None:
        return None, _invalid_app_from_path(
            spec_path,
            app_id=app_id,
            name=name,
            recommended_server_id=recommended_server_id,
            transport=transport,
            validation_error=(
                "Invalid app spec: `command` must be a non-empty string for stdio apps."
            ),
        )

    preview = None
    if preview_payload is not None:
        if not isinstance(preview_payload, dict):
            return None, _invalid_app_from_path(
                spec_path,
                app_id=app_id,
                name=name,
                recommended_server_id=recommended_server_id,
                transport=transport,
                validation_error=(
                    "Invalid app spec: `preview_tool` must be a JSON object with "
                    "`name` and `arguments`."
                ),
            )
        tool_name = _as_optional_str(preview_payload.get("name"))
        arguments = preview_payload.get("arguments")
        if tool_name is None or not isinstance(arguments, dict):
            return None, _invalid_app_from_path(
                spec_path,
                app_id=app_id,
                name=name,
                recommended_server_id=recommended_server_id,
                transport=transport,
                validation_error=(
                    "Invalid app spec: `preview_tool` requires a non-empty `name` "
                    "and object `arguments`."
                ),
            )
        preview = CodexMcpAppPreviewConfig(
            tool_name=tool_name,
            arguments={
                str(key): _json_ready(value) for key, value in arguments.items()
            },
        )

    try:
        resolved_command = _resolve_template(
            command_text,
            repo_root=repo_root,
            projects_root=projects_root,
        )
        resolved_args = tuple(
            _resolve_template(
                str(item),
                repo_root=repo_root,
                projects_root=projects_root,
            )
            for item in args_payload
        )
        resolved_env = tuple(
            sorted(
                (
                    str(key),
                    _resolve_template(
                        str(value),
                        repo_root=repo_root,
                        projects_root=projects_root,
                    ),
                )
                for key, value in env_payload.items()
            )
        )
    except _TemplateResolutionError as exc:
        return None, _invalid_app_from_path(
            spec_path,
            app_id=app_id,
            name=name,
            recommended_server_id=recommended_server_id,
            transport=transport,
            validation_error=str(exc),
        )

    return CodexMcpAppSpec(
        app_id=app_id,
        name=name,
        description=description,
        recommended_server_id=recommended_server_id,
        transport=transport,
        command=resolved_command,
        args=resolved_args,
        env=resolved_env,
        tags=tuple(
            str(item).strip() for item in (tags_payload or []) if str(item).strip()
        ),
        supports_ui_extension=bool(payload.get("supports_ui_extension", False)),
        ui_entry_uri=_as_optional_str(payload.get("ui_entry_uri")),
        spec_path=str(spec_path),
        preview=preview,
    ), None


def _require_installable_app(
    *,
    requested_app_id: str,
    repo_root: Path | None,
    projects_root: str,
) -> CodexMcpAppSpec:
    discovery = _discover_repo_mcp_apps(
        repo_root=repo_root,
        projects_root=projects_root,
    )
    for app in discovery.valid_specs:
        if app.app_id == requested_app_id:
            return app
    for app in discovery.invalid_apps:
        if app.app_id == requested_app_id:
            detail = app.validation_error or "MCP app configuration is invalid."
            raise RuntimeError(
                f"MCP app `{requested_app_id}` is not installable. {detail}"
            )
    raise ValueError(f"MCP app `{requested_app_id}` was not found in this repository.")


def _remove_server(command: str, server_id: str) -> None:
    completed, command_error = _run_mcp_subprocess(
        command,
        ["mcp", "remove", server_id],
        timeout=_MCP_REMOVE_SERVER_TIMEOUT_SECONDS,
        timeout_message=(
            "`codex mcp remove` timed out while removing the stored server config."
        ),
        exec_failure_message=(
            "`codex mcp remove` could not be executed while removing the stored "
            "server config."
        ),
    )
    if command_error is not None:
        raise RuntimeError(command_error)
    if completed.returncode != 0:
        detail = _sanitize_diagnostic_text(
            completed.stderr.strip()
            or completed.stdout.strip()
            or (f"`codex mcp remove` exited with code {completed.returncode}.")
        )
        raise RuntimeError(detail)


def _add_stdio_server(
    command: str,
    *,
    server_id: str,
    launch_command: str,
    launch_args: tuple[str, ...],
    launch_env: tuple[tuple[str, str], ...],
) -> None:
    process_args = [*shlex.split(command), "mcp", "add", server_id]
    for key, value in launch_env:
        process_args.extend(["--env", f"{key}={value}"])
    process_args.append("--")
    process_args.append(launch_command)
    process_args.extend(launch_args)

    completed, command_error = _run_mcp_subprocess(
        command,
        process_args[len(shlex.split(command)) :],
        timeout=_MCP_ADD_SERVER_TIMEOUT_SECONDS,
        timeout_message=(
            "`codex mcp add` timed out while installing the desired server config."
        ),
        exec_failure_message=(
            "`codex mcp add` could not be executed while installing the desired "
            "server config."
        ),
        full_process_args=process_args,
    )
    if command_error is not None:
        raise RuntimeError(command_error)
    if completed.returncode != 0:
        detail = _sanitize_diagnostic_text(
            completed.stderr.strip()
            or completed.stdout.strip()
            or (f"`codex mcp add` exited with code {completed.returncode}.")
        )
        raise RuntimeError(detail)


def _rollback_previous_server_config(
    command: str,
    previous_config: CodexInstalledMcpServerConfig,
) -> str | None:
    restore_error = _restore_capability_error(previous_config)
    if restore_error is not None:
        return restore_error
    try:
        _add_stdio_server(
            command,
            server_id=previous_config.server_id,
            launch_command=previous_config.command,
            launch_args=previous_config.args,
            launch_env=previous_config.env,
        )
    except RuntimeError as exc:
        return str(exc)
    return None


def _restore_capability_error(
    installed_config: CodexInstalledMcpServerConfig,
) -> str | None:
    if installed_config.transport != "stdio":
        return (
            "the stored transport "
            f"`{installed_config.transport}` cannot be restored by this backend if "
            "the update fails."
        )
    if installed_config.command is None:
        return "the previous stdio command is missing from the stored config."
    if installed_config.args is None:
        return "the previous stdio args are missing from the stored config."
    if installed_config.env is None:
        return "the previous stdio env is missing from the stored config."
    return None


def get_installed_mcp_server_lookup(
    command: str,
    server_id: str,
) -> CodexInstalledMcpServerLookup:
    completed, command_error = _run_mcp_subprocess(
        command,
        ["mcp", "get", server_id, "--json"],
        timeout=_MCP_GET_SERVER_TIMEOUT_SECONDS,
        timeout_message=(
            "`codex mcp get --json` timed out while checking the existing server "
            "config."
        ),
        exec_failure_message=(
            "`codex mcp get --json` could not be executed while checking the "
            "existing server config."
        ),
    )
    if command_error is not None:
        return CodexInstalledMcpServerLookup(
            status="unreadable",
            server_present=False,
            server_presence_known=False,
            error=command_error,
        )
    if completed.returncode != 0:
        output_text = f"{completed.stderr}\n{completed.stdout}".strip()
        if _looks_like_missing_server(output_text):
            return CodexInstalledMcpServerLookup(
                status="missing",
                server_present=False,
                server_presence_known=True,
            )
        return CodexInstalledMcpServerLookup(
            status="unreadable",
            server_present=False,
            server_presence_known=False,
            error="`codex mcp get --json` failed while checking the existing server config.",
        )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return CodexInstalledMcpServerLookup(
            status="unreadable",
            server_present=True,
            server_presence_known=True,
            error="`codex mcp get --json` returned malformed JSON.",
        )
    if not isinstance(payload, dict):
        return CodexInstalledMcpServerLookup(
            status="unreadable",
            server_present=True,
            server_presence_known=True,
            error="`codex mcp get --json` returned an unsupported payload shape.",
        )
    enabled = payload.get("enabled")
    if not isinstance(enabled, bool):
        return CodexInstalledMcpServerLookup(
            status="unreadable",
            server_present=True,
            server_presence_known=True,
            error="`codex mcp get --json` returned an unsupported payload shape.",
        )
    raw_disabled_reason = payload.get("disabled_reason")
    disabled_reason = None
    if raw_disabled_reason is not None:
        disabled_reason = _sanitize_diagnostic_text(str(raw_disabled_reason).strip())
        if not disabled_reason:
            disabled_reason = None
    transport = payload.get("transport")
    if not isinstance(transport, dict):
        return CodexInstalledMcpServerLookup(
            status="unreadable",
            server_present=True,
            server_presence_known=True,
            error="`codex mcp get --json` returned an unsupported payload shape.",
        )
    transport_type = _as_optional_str(transport.get("type"))
    if transport_type is None:
        return CodexInstalledMcpServerLookup(
            status="unreadable",
            server_present=True,
            server_presence_known=True,
            error="`codex mcp get --json` returned an unsupported payload shape.",
        )
    command_value: str | None = None
    args_value: tuple[str, ...] | None = None
    env_value: tuple[tuple[str, str], ...] | None = None
    if transport_type == "stdio":
        raw_command = _as_optional_str(transport.get("command"))
        raw_args = transport.get("args")
        raw_env = transport.get("env")
        if raw_command is None:
            return CodexInstalledMcpServerLookup(
                status="unreadable",
                server_present=True,
                server_presence_known=True,
                error="`codex mcp get --json` returned an unsupported stdio payload shape.",
            )
        if not isinstance(raw_args, list) or not isinstance(raw_env, dict):
            return CodexInstalledMcpServerLookup(
                status="unreadable",
                server_present=True,
                server_presence_known=True,
                error="`codex mcp get --json` returned an unsupported stdio payload shape.",
            )
        command_value = raw_command
        args_value = tuple(str(item) for item in raw_args)
        env_value = tuple(
            sorted((str(key), str(value)) for key, value in raw_env.items())
        )
    return CodexInstalledMcpServerLookup(
        status="present",
        server_present=True,
        server_presence_known=True,
        config=CodexInstalledMcpServerConfig(
            server_id=server_id,
            enabled=enabled,
            disabled_reason=disabled_reason,
            transport=transport_type,
            transport_payload=_json_ready(transport),
            command=command_value,
            args=args_value,
            env=env_value,
        ),
    )


def _run_mcp_subprocess(
    command: str,
    args: list[str],
    *,
    timeout: float,
    timeout_message: str,
    exec_failure_message: str,
    full_process_args: list[str] | None = None,
) -> tuple[subprocess.CompletedProcess[str] | None, str | None]:
    process_args = full_process_args or [*shlex.split(command), *args]
    try:
        completed = subprocess.run(
            process_args,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return None, timeout_message
    except (FileNotFoundError, OSError):
        return None, exec_failure_message
    return completed, None


def _diff_installed_config(
    app: CodexMcpAppSpec,
    installed_config: CodexInstalledMcpServerConfig,
) -> str | None:
    diffs: list[str] = []
    if installed_config.transport != app.transport:
        diffs.append(
            f"transport stored as `{installed_config.transport}` but repo app expects `{app.transport}`"
        )
        return "; ".join(diffs)
    if installed_config.command != app.command:
        diffs.append(
            f"command stored as `{installed_config.command}` but repo app expects `{app.command}`"
        )
    if installed_config.args != app.args:
        diffs.append(
            "args differ between the stored Codex config and the repo app spec"
        )
    if installed_config.env != app.env:
        diffs.append(
            "env differs between the stored Codex config and the repo app spec"
        )
    if not diffs:
        return None
    return "; ".join(diffs)


def _inspect_app(
    app: CodexMcpAppSpec,
    *,
    installed_lookup: CodexInstalledMcpServerLookup | None = None,
    installed_config: CodexInstalledMcpServerConfig | None = None,
) -> CodexMcpApp:
    if installed_lookup is None:
        if installed_config is None:
            installed_lookup = CodexInstalledMcpServerLookup(
                status="missing",
                server_present=False,
                server_presence_known=True,
            )
        else:
            installed_lookup = CodexInstalledMcpServerLookup(
                status="present",
                server_present=True,
                server_presence_known=True,
                config=installed_config,
            )
    installed_config = installed_lookup.config
    try:
        tools, resources, prompts, preview = asyncio.run(
            asyncio.wait_for(
                _inspect_app_async(app),
                timeout=_MCP_APP_TOTAL_INSPECTION_TIMEOUT_SECONDS,
            )
        )
        protocol_error = None
    except TimeoutError:
        tools = ()
        resources = ()
        prompts = ()
        preview = None
        protocol_error = (
            "Timed out inspecting this MCP app after "
            f"{_MCP_APP_TOTAL_INSPECTION_TIMEOUT_SECONDS:.1f}s."
        )
    except Exception as exc:
        tools = ()
        resources = ()
        prompts = ()
        preview = None
        protocol_error = _format_protocol_error_for_app(exc, app)

    config_matches = (
        _diff_installed_config(app, installed_config) is None
        if installed_config is not None
        else None
    )

    if installed_lookup.status == "unreadable":
        install_state = "unreadable"
    elif protocol_error is not None:
        install_state = "protocol-broken"
    elif installed_config is None:
        install_state = "missing"
    elif not installed_config.enabled:
        install_state = "disabled"
    else:
        install_state = "matching" if config_matches else "drifted"
    drift_summary = (
        _diff_installed_config(app, installed_config)
        if installed_config is not None and config_matches is False
        else None
    )

    return CodexMcpApp(
        app_id=app.app_id,
        name=app.name,
        description=app.description,
        recommended_server_id=app.recommended_server_id,
        transport=app.transport,
        command=app.command,
        args=app.args,
        env=app.env,
        tags=app.tags,
        supports_ui_extension=app.supports_ui_extension,
        ui_entry_uri=app.ui_entry_uri,
        spec_path=app.spec_path,
        installed=install_state == "matching",
        install_state=install_state,
        server_present=installed_lookup.server_present,
        server_presence_known=installed_lookup.server_presence_known,
        config_matches=config_matches,
        tools=tools,
        resources=resources,
        prompts=prompts,
        preview=preview,
        drift_summary=drift_summary,
        disabled_reason=installed_config.disabled_reason
        if installed_config is not None
        else None,
        lookup_error=installed_lookup.error,
        protocol_error=protocol_error,
    )


async def _inspect_app_async(
    app: CodexMcpAppSpec,
) -> tuple[
    tuple[CodexMcpAppTool, ...],
    tuple[CodexMcpAppResource, ...],
    tuple[CodexMcpAppPrompt, ...],
    CodexMcpAppPreview | None,
]:
    params = StdioServerParameters(
        command=app.command,
        args=list(app.args),
        env={**os.environ, **dict(app.env)},
    )
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await _await_with_timeout(
                session.initialize(),
                stage="initialize",
            )
            tools_result = await _await_with_timeout(
                session.list_tools(),
                stage="tools/list",
            )
            resources_result = await _await_with_timeout(
                session.list_resources(),
                stage="resources/list",
            )
            prompts_result = await _await_with_timeout(
                session.list_prompts(),
                stage="prompts/list",
            )
            preview = None
            if app.preview is not None:
                tool_result = await _await_with_timeout(
                    session.call_tool(
                        app.preview.tool_name,
                        arguments=app.preview.arguments,
                    ),
                    stage=f"tools/call:{app.preview.tool_name}",
                )
                preview = CodexMcpAppPreview(
                    tool_name=app.preview.tool_name,
                    arguments=app.preview.arguments,
                    result=(
                        _json_ready(tool_result.structuredContent)
                        if tool_result.structuredContent is not None
                        else _json_ready(tool_result.content)
                    ),
                    is_error=tool_result.isError,
                    error="Tool call returned an error."
                    if tool_result.isError
                    else None,
                )
            return (
                tuple(_tool_from_sdk(tool) for tool in tools_result.tools),
                tuple(
                    _resource_from_sdk(resource)
                    for resource in resources_result.resources
                ),
                tuple(_prompt_from_sdk(prompt) for prompt in prompts_result.prompts),
                preview,
            )


def _tool_from_sdk(tool: Any) -> CodexMcpAppTool:
    annotations = getattr(tool, "annotations", None)
    return CodexMcpAppTool(
        name=tool.name,
        title=getattr(tool, "title", None),
        description=getattr(tool, "description", None),
        read_only=bool(getattr(annotations, "readOnlyHint", False)),
        destructive=bool(getattr(annotations, "destructiveHint", False)),
        idempotent=bool(getattr(annotations, "idempotentHint", False)),
        open_world=bool(getattr(annotations, "openWorldHint", False)),
        input_schema=_json_ready(getattr(tool, "inputSchema", {}) or {}),
    )


def _resource_from_sdk(resource: Any) -> CodexMcpAppResource:
    return CodexMcpAppResource(
        name=resource.name,
        title=getattr(resource, "title", None),
        uri=str(resource.uri),
        description=getattr(resource, "description", None),
        mime_type=getattr(resource, "mimeType", None),
    )


def _prompt_from_sdk(prompt: Any) -> CodexMcpAppPrompt:
    arguments = getattr(prompt, "arguments", None) or []
    return CodexMcpAppPrompt(
        name=prompt.name,
        title=getattr(prompt, "title", None),
        description=getattr(prompt, "description", None),
        arguments=tuple(
            CodexMcpAppPromptArgument(
                name=argument.name,
                description=getattr(argument, "description", None),
                required=bool(getattr(argument, "required", False)),
            )
            for argument in arguments
        ),
    )


async def _await_with_timeout(
    awaitable: Any,
    *,
    stage: str,
) -> Any:
    try:
        return await asyncio.wait_for(
            awaitable,
            timeout=_MCP_APP_STEP_TIMEOUT_SECONDS,
        )
    except TimeoutError as exc:
        raise TimeoutError(
            f"Timed out during `{stage}` after {_MCP_APP_STEP_TIMEOUT_SECONDS:.1f}s."
        ) from exc


def _resolve_template(
    value: str,
    *,
    repo_root: Path | None,
    projects_root: str,
) -> str:
    resolved_repo_root = str(repo_root.resolve()) if repo_root is not None else ""
    try:
        return value.format(
            repo_root=resolved_repo_root,
            projects_root=projects_root,
        )
    except KeyError as exc:
        placeholder = exc.args[0] if exc.args else "unknown"
        raise _TemplateResolutionError(
            "Invalid app spec template: unknown placeholder "
            f"`{{{placeholder}}}` in `{value}`."
        ) from exc
    except (IndexError, ValueError) as exc:
        raise _TemplateResolutionError(
            f"Invalid app spec template `{value}`. {exc}"
        ) from exc


def _format_command_preview(command: str, args: tuple[str, ...]) -> str:
    return " ".join([command, *args]).strip()


def _json_ready(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if hasattr(value, "model_dump"):
        return _json_ready(value.model_dump(mode="json"))
    return str(value)


def _as_optional_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _app_field_value(
    payload: dict[str, object],
    *,
    field_name: str,
    default_value: str,
) -> str:
    raw_value = payload.get(field_name)
    parsed = _as_optional_str(raw_value)
    if raw_value is None:
        return default_value
    if parsed is None:
        return default_value
    return parsed


def _invalid_app_from_path(
    spec_path: Path,
    *,
    app_id: str,
    name: str,
    validation_error: str,
    recommended_server_id: str | None = None,
    transport: str = "stdio",
) -> CodexMcpApp:
    return CodexMcpApp(
        app_id=app_id,
        name=name,
        description="",
        recommended_server_id=recommended_server_id or app_id,
        transport=transport,
        command="",
        args=(),
        env=(),
        tags=(),
        supports_ui_extension=False,
        ui_entry_uri=None,
        spec_path=str(spec_path),
        installed=False,
        install_state="invalid",
        server_present=False,
        server_presence_known=False,
        config_matches=None,
        tools=(),
        resources=(),
        prompts=(),
        preview=None,
        drift_summary=None,
        disabled_reason=None,
        lookup_error=None,
        validation_error=validation_error,
        protocol_error=None,
    )


def _invalid_app_from_spec(
    spec: CodexMcpAppSpec,
    *,
    validation_error: str,
) -> CodexMcpApp:
    return CodexMcpApp(
        app_id=spec.app_id,
        name=spec.name,
        description=spec.description,
        recommended_server_id=spec.recommended_server_id,
        transport=spec.transport,
        command=spec.command,
        args=spec.args,
        env=spec.env,
        tags=spec.tags,
        supports_ui_extension=spec.supports_ui_extension,
        ui_entry_uri=spec.ui_entry_uri,
        spec_path=spec.spec_path,
        installed=False,
        install_state="invalid",
        server_present=False,
        server_presence_known=False,
        config_matches=None,
        tools=(),
        resources=(),
        prompts=(),
        preview=None,
        drift_summary=None,
        disabled_reason=None,
        lookup_error=None,
        validation_error=validation_error,
        protocol_error=None,
    )


def _find_duplicate_values(
    apps: list[CodexMcpAppSpec],
    *,
    value_getter: Any,
) -> dict[str, list[CodexMcpAppSpec]]:
    collisions: dict[str, list[CodexMcpAppSpec]] = {}
    seen: dict[str, list[CodexMcpAppSpec]] = {}
    for app in apps:
        value = value_getter(app)
        bucket = seen.setdefault(value, [])
        bucket.append(app)
    for value, specs in seen.items():
        if len(specs) > 1:
            collisions[value] = specs
    return collisions


def _format_protocol_error(exc: BaseException) -> str:
    leaf_messages = _leaf_exception_messages(exc)
    if leaf_messages:
        return leaf_messages[0]
    message = str(exc).strip()
    if message and "TaskGroup" not in message and "sub-exception" not in message:
        return message
    return exc.__class__.__name__


def _format_protocol_error_for_app(
    exc: BaseException,
    app: CodexMcpAppSpec,
) -> str:
    message = _format_protocol_error(exc)
    if message in {"Connection closed", "ClosedResourceError"}:
        launch_error = _probe_launch_failure(app)
        if launch_error is not None:
            return launch_error
    return message


def _looks_like_missing_server(message: str) -> bool:
    normalized = message.lower()
    return (
        "no mcp server named" in normalized
        or "unknown mcp server" in normalized
        or "no such mcp server" in normalized
        or "mcp server not found" in normalized
        or "server not found" in normalized
    )


def _disabled_reason_detail(disabled_reason: str | None) -> str:
    if disabled_reason is None:
        return ""
    return f"Stored server is disabled: {disabled_reason}. "


def _sanitize_diagnostic_text(text: str) -> str:
    sanitized = text
    sanitized = sanitized.replace("Bearer secret", "Bearer [redacted]")
    sanitized = sanitized.replace("Bearer token", "Bearer [redacted]")
    import re

    sanitized = re.sub(
        r"(Bearer)\s+[A-Za-z0-9._~+/=-]+",
        r"\1 [redacted]",
        sanitized,
        flags=re.IGNORECASE,
    )
    sanitized = re.sub(
        r'("Authorization"\s*:\s*")([^"]+)(")',
        r"\1[redacted]\3",
        sanitized,
        flags=re.IGNORECASE,
    )
    sanitized = re.sub(
        r"(Authorization\s*[:=]\s*)([^,;]+)",
        r"\1[redacted]",
        sanitized,
        flags=re.IGNORECASE,
    )
    sanitized = re.sub(
        r"([?&](?:token|access_token|api_key|authorization)=)([^&\s]+)",
        r"\1[redacted]",
        sanitized,
        flags=re.IGNORECASE,
    )
    return sanitized


def _leaf_exception_messages(exc: BaseException) -> list[str]:
    if isinstance(exc, BaseExceptionGroup):
        messages: list[str] = []
        for sub_exc in exc.exceptions:
            messages.extend(_leaf_exception_messages(sub_exc))
        return messages

    for nested in (exc.__cause__, exc.__context__):
        if nested is not None:
            nested_messages = _leaf_exception_messages(nested)
            if nested_messages:
                return nested_messages

    message = str(exc).strip()
    if not message:
        return [exc.__class__.__name__]
    if "TaskGroup" in message and "sub-exception" in message:
        return [exc.__class__.__name__]
    return [message]


def _probe_launch_failure(app: CodexMcpAppSpec) -> str | None:
    try:
        completed = subprocess.run(
            [app.command, *app.args],
            capture_output=True,
            check=False,
            text=True,
            timeout=1,
            env={**os.environ, **dict(app.env)},
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode == 0:
        return None
    detail = completed.stderr.strip() or completed.stdout.strip()
    if not detail:
        return None
    return detail.splitlines()[0].strip()
