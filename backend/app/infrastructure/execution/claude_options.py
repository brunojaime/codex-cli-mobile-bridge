"""Translate portable legacy options without relaxing their restrictions."""
from __future__ import annotations

import json
from pathlib import Path
import re
import tomllib

from backend.app.domain.entities.codex_options import CodexRunOptions


def resolve_skill(skill: str, workdir: str | None) -> Path | None:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", skill) or skill in {".", ".."}:
        return None
    roots = [Path.home()/".codex/skills", Path.home()/".agents/skills"]
    if workdir:
        roots += [Path(workdir)/".codex/skills", Path(workdir)/"codex-skills"]
    return next((root/skill/"SKILL.md" for root in roots if (root/skill/"SKILL.md").is_file()), None)


def translate_options(options: CodexRunOptions | None, *, workdir: str | None) -> tuple[list[str], str]:
    if options is None or options.is_empty():
        return [], ""
    options = options.normalized()
    if options.profile:
        raise ValueError("Codex configuration profiles have no automatic Claude equivalent. Use backend AI configuration.")
    # MCP authentication/permissions are provider-owned. Never silently drop a selection.
    if options.mcp_server_ids:
        raise ValueError("Selected Codex MCP servers require a Claude mapping; configure them for Claude before use.")
    overrides = {}
    for item in options.config_overrides:
        try:
            parsed = tomllib.loads(item)
        except tomllib.TOMLDecodeError as exc:
            raise ValueError("Invalid AI option") from exc
        if len(parsed) != 1:
            raise ValueError("Each AI override must contain exactly one setting")
        for key, value in parsed.items():
            if key in {"features", "mcp_servers"} and isinstance(value, dict):
                overrides.setdefault(key, {}).update(value)
            elif key in overrides:
                raise ValueError("Duplicate AI option")
            else:
                overrides[key] = value
    readonly = overrides.pop("sandbox_mode", None)
    approval = overrides.pop("approval_policy", None)
    search = overrides.pop("web_search", None)
    # Reasoning is owned by backend AI_EFFORT; legacy frontend hints cannot override it.
    effort = overrides.pop("model_reasoning_effort", None)
    if effort not in {None, "low", "medium", "high", "xhigh", "max", "minimal", "none"}:
        raise ValueError("Unsupported reasoning option")
    if readonly not in {None, "read-only"}:
        raise ValueError("Claude cannot reproduce this Codex sandbox mode automatically")
    if approval not in {None, "never"}:
        raise ValueError("Claude cannot reproduce this approval policy automatically")
    if search not in {None, "disabled"}:
        raise ValueError("Unsupported legacy web-search policy")
    features = overrides.pop("features", {})
    mcp = overrides.pop("mcp_servers", {})
    no_tools = bool(features)
    # Legacy analyzer disables all tools. Accept only restrictions, never enables.
    if (not isinstance(features, dict) or any(value is not False for value in features.values())
            or not isinstance(mcp, dict)
            or any(value != {"enabled": False} for value in mcp.values()) or overrides):
        raise ValueError("Unsupported Codex configuration option for Claude")
    args = []
    if readonly == "read-only" or no_tools:
        # Safe mode disables hooks/plugins; strict MCP disables external tool side effects.
        # Restricted mode confines file tools to workspace. This is a tool allowlist,
        # not a claim that Claude implements Codex's OS sandbox.
        args += ["--safe-mode", "--restricted", "--strict-mcp-config", "--tools",
                 "" if no_tools else "Read,Glob,Grep", "--permission-mode", "dontAsk"]
    elif approval == "never":
        args += ["--permission-mode", "dontAsk"]
    if mcp and readonly != "read-only" and not no_tools:
        args += ["--strict-mcp-config"]
    if search == "disabled":
        args += ["--disallowedTools", "WebSearch,WebFetch"]
    context = []
    if options.search_enabled:
        if readonly or no_tools or search == "disabled":
            raise ValueError("Search conflicts with the requested read-only/no-tools policy")
        args += ["--allowedTools", "WebSearch"]
        context.append("Web search was requested; use WebSearch when relevant.")
    for skill in options.skill_ids:
        if not re.fullmatch(r"[A-Za-z0-9._-]+", skill):
            raise ValueError("Invalid skill identifier")
        path = resolve_skill(skill, workdir)
        if path is None:
            raise ValueError(f"Selected skill is unavailable: {skill}")
        content = path.read_text(encoding="utf-8")
        if len(content) > 100_000:
            raise ValueError(f"Selected skill is too large: {skill}")
        context.append(f"Selected skill {json.dumps(skill)} ({path.resolve()}):\n{content}")
        if not no_tools:
            args += ["--add-dir", str(path.parent.resolve())]
    return args, "\n\n".join(context)
