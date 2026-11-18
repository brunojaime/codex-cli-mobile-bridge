"""Bounded recovery decisions. Command output is never a model instruction."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path


def operator_hints(argv, workspace, since):
    """Read only known operator failure logs; never backups or credential files.

    Several legacy adapters mask their subprocess errors. Their private logs are
    used only by the structural classifier, never included in agent context.
    """
    scripts = {Path(a).name for a in argv if a.endswith((".py", ".mjs"))}
    known = {"gestion_dev_delivery.mjs", "cloudflare_app_delivery.mjs",
             "nienfos_web_delivery.py", "alas_brasas_delivery.mjs", "bridge_dev_delivery.py"}
    if not scripts & known:
        return ""
    configuration = next((Path(a) for a in argv if Path(a).name == "config.json"), None)
    if not configuration:
        return ""
    try:
        settings = json.loads(configuration.read_text())
        state = Path(settings["state"])
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=workspace,
                                           text=True, stderr=subprocess.DEVNULL, timeout=10).strip()
        paths = list(state.glob("*.log")) + list((state / revision).glob("*.log"))
        recent = sorted((p for p in paths if p.is_file() and p.stat().st_mtime >= since),
                        key=lambda p: p.stat().st_mtime, reverse=True)[:4]
        output = "\n".join(p.read_bytes()[-500000:].decode(errors="replace") for p in recent)
        for name, expected in settings.get("trustedFiles", {}).items():
            try:
                actual = hashlib.sha256((Path(workspace) / name).read_bytes()).hexdigest()
            except OSError:
                actual = None
            if actual != expected:
                output += "\nOfficial gate changed"
        for name, expected in settings.get("pinned", {}).items():
            try:
                actual = hashlib.sha256((Path(workspace) / name).read_bytes()).hexdigest()
            except OSError:
                actual = None
            if actual != expected:
                output += "\nDestination/dependency changed"
        if scripts & {"gestion_dev_delivery.mjs", "cloudflare_app_delivery.mjs"} and not (state / revision / "evidence/review.json").exists():
            output += "\nFileNotFoundError: review.json"
        return output
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        return ""


def command_diagnostic(*, stage, index, argv, returncode, output, revision, workspace=None):
    # Classify without copying arbitrary command output (which can contain secrets).
    lowered = output.lower()
    category = "validation_failed"
    if any(s in lowered for s in ("unauthorized", "authentication", "invalid token", "error code: 10000", "not logged in")):
        category = "credentials_required"
    elif any(s in lowered for s in ("previous publication attempt", "uncertain-reconcile", "reconcile before retry")):
        category = "publication_uncertain"
    elif any(s in lowered for s in ("official gate changed", "destination/dependency", "changed outside", "unapproved publication")):
        category = "operator_setup_required"
    elif "review.json" in lowered and any(s in lowered for s in ("enoent", "no such file", "filenotfound")):
        category = "review_evidence_missing"
    elif returncode == "timeout":
        category = "command_timeout"
    elif returncode == "unavailable":
        category = "operator_setup_required"
    # A command identifier is operator configuration, never its arguments/values.
    command = next((Path(a).name for a in argv[1:] if a.endswith((".py", ".mjs", ".js"))), Path(argv[0]).name)
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", command):
        command = "configured-command"
    data = {"stage": stage, "index": index, "command": command,
            "returncode": returncode, "category": category, "revision": revision}
    data["error_types"] = sorted(set(re.findall(
        r"\b(AssertionError|SyntaxError|TypeError|ReferenceError|RangeError|ModuleNotFoundError|FileNotFoundError|TimeoutError)\b", output)))
    locations = []
    if workspace:
        root = Path(workspace).resolve()
        matches = re.findall(r'File "([^"\n]+)", line (\d+)', output)
        matches += re.findall(r"([\w./-]+\.(?:py|mjs|js|ts|dart|svelte)):(\d+)(?::\d+)?", output)
        for name, line in matches:
            candidate = (root / name).resolve()
            if not candidate.is_relative_to(root):
                continue
            relative = candidate.relative_to(root)
            if (candidate.is_file() and not any(p.startswith('.') or p in {'node_modules', 'vendor'} for p in relative.parts)
                    and candidate.suffix in {'.py', '.mjs', '.js', '.ts', '.dart', '.svelte'}
                    and re.fullmatch(r"[A-Za-z0-9_./\[\]-]+", str(relative))):
                location = f"{relative}:{int(line)}"
                if location not in locations:
                    locations.append(location)
        data["locations"] = locations[:12]
    data["fingerprint"] = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    return data


def recovery_decision(failure, *, recoveries, limit, stopped):
    if stopped:
        return "user_stopped"
    if recoveries >= limit:
        return "attempts_exhausted"
    if not failure:
        # Legacy generic failures may have occurred after a publication started.
        return "diagnosis_required"
    if failure["stage"] != "validate":
        return "publication_needs_reconciliation"
    if failure["category"] in {"credentials_required", "publication_uncertain", "operator_setup_required"}:
        return failure["category"]
    return "repair"
