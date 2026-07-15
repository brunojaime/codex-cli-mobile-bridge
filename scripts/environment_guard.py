#!/usr/bin/env python3
"""Fail-closed environment boundary guard with JSONL audit logging."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import uuid


VALID_ENVIRONMENTS = {"dev", "prod", "control"}
DEFAULT_ENVIRONMENT = "dev"


@dataclass(frozen=True)
class GuardDecision:
    allowed: bool
    reason: str
    current_environment: str
    target_environment: str


def decide(
    *,
    current_environment: str | None,
    target_environment: str,
) -> GuardDecision:
    current = _normalize_environment(current_environment or DEFAULT_ENVIRONMENT)
    target = _normalize_environment(target_environment)

    if current not in VALID_ENVIRONMENTS:
        return GuardDecision(False, "invalid_current_environment", current, target)
    if target not in VALID_ENVIRONMENTS:
        return GuardDecision(False, "invalid_target_environment", current, target)
    if current == "control":
        return GuardDecision(True, "control_environment_allowed", current, target)
    if current == target:
        return GuardDecision(True, "same_environment_allowed", current, target)
    return GuardDecision(False, "environment_boundary_violation", current, target)


def audit_event(
    *,
    operation: str,
    action: str,
    decision: GuardDecision,
    audit_log: Path,
) -> dict[str, object]:
    event = {
        "kind": "codex.environmentGuardAudit",
        "version": 1,
        "event_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "operation": operation,
        "action": action,
        "current_environment": decision.current_environment,
        "target_environment": decision.target_environment,
        "allowed": decision.allowed,
        "reason": decision.reason,
        "actor": _actor(),
        "hostname": socket.gethostname(),
        "cwd": str(Path.cwd()),
        "git_commit": _git_commit(),
    }
    audit_log.parent.mkdir(parents=True, exist_ok=True)
    with audit_log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")
    return event


def default_audit_log() -> Path:
    configured = os.environ.get("CODEX_ENVIRONMENT_AUDIT_LOG")
    if configured:
        return Path(configured)
    repo_root = Path(__file__).resolve().parents[1]
    return repo_root / ".data" / "audit" / "environment_guard.jsonl"


def resolve_current_environment() -> str:
    return (
        os.environ.get("CODEX_BRIDGE_ENVIRONMENT")
        or os.environ.get("BRIDGE_ENVIRONMENT")
        or DEFAULT_ENVIRONMENT
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Block dev/prod boundary crossings and write an audit event."
    )
    parser.add_argument("--operation", required=True)
    parser.add_argument("--target-environment", required=True)
    parser.add_argument(
        "--action",
        choices=["read", "write", "deploy", "release"],
        default="write",
    )
    parser.add_argument("--current-environment")
    parser.add_argument("--audit-log", type=Path)
    args = parser.parse_args()

    decision = decide(
        current_environment=args.current_environment or resolve_current_environment(),
        target_environment=args.target_environment,
    )
    audit_log = args.audit_log or default_audit_log()
    try:
        event = audit_event(
            operation=args.operation,
            action=args.action,
            decision=decision,
            audit_log=audit_log,
        )
    except OSError as exc:
        payload = {
            "kind": "codex.environmentGuardResult",
            "ok": False,
            "allowed": False,
            "reason": "audit_log_write_failed",
            "error": str(exc),
            "audit_log": str(audit_log),
        }
        print(json.dumps(payload, sort_keys=True), file=sys.stderr)
        return 4

    payload = {
        "kind": "codex.environmentGuardResult",
        "ok": decision.allowed,
        "allowed": decision.allowed,
        "reason": decision.reason,
        "audit_log": str(audit_log),
        "event_id": event["event_id"],
        "current_environment": decision.current_environment,
        "target_environment": decision.target_environment,
        "operation": args.operation,
        "action": args.action,
    }
    print(json.dumps(payload, sort_keys=True))
    return 0 if decision.allowed else 3


def _normalize_environment(value: str) -> str:
    return value.strip().lower().replace("_", "-")


def _actor() -> str:
    for key in ("GITHUB_ACTOR", "CODEX_ACTOR", "USER", "USERNAME"):
        value = os.environ.get(key)
        if value:
            return value
    return "unknown"


def _git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


if __name__ == "__main__":
    raise SystemExit(main())
