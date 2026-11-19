"""Forward WhatsApp batches of an "ideas" project to the idea pipeline (Lenovo, factory-lab).

A project opts in with ``<workspace>/.codex/integrations/ideas-pipeline.json``::

    {"version": 1, "enabled": true,
     "url": "https://<lenovo>.ts.net:8797/ideas",
     "token_file": "~/.config/nienfos/idea-pipeline.token",
     "dry_run": false}

When enabled, the worker skips semantic triage and the planning chat for that project and
POSTs the settled batch (texts, audio transcripts, media) to the pipeline instead. Nothing is
ever sent to WhatsApp. ``dry_run`` writes the payload to ``<data>/ideas-forward/outbox`` without
any network call, which is how the route is tested before the Lenovo side is exposed.

Idempotency: the pipeline derives the idea id from group id + message ids, so a re-delivery
after an uncertain POST is harmless. A failed attempt is retried no sooner than
``RETRY_SECONDS`` later, and each record gets the usual ``codex-submission.json`` marker only
after the pipeline accepted the batch.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

CONFIG_RELATIVE = Path(".codex") / "integrations" / "ideas-pipeline.json"
SUBMISSION_FILENAME = "codex-submission.json"
ATTEMPT_FILENAME = "ideas-forward-attempt.json"
RETRY_SECONDS = 60.0
MAX_MEDIA_BYTES = 25 * 1024 * 1024
SCHEMA = "nienfos.ideas-forward/1"


@dataclass(frozen=True, slots=True)
class IdeasForwardConfig:
    url: str | None
    token_file: Path | None
    dry_run: bool
    timeout_seconds: float = 30.0


def ideas_config(workspace: Path) -> IdeasForwardConfig | None:
    """Return the opt-in config, or None when the project uses the regular flow."""
    filename = workspace / CONFIG_RELATIVE
    try:
        value = json.loads(filename.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or value.get("version") != 1 or value.get("enabled") is not True:
        return None
    dry_run = value.get("dry_run") is True
    url = str(value.get("url") or "").strip() or None
    if not dry_run and (not url or not url.startswith(("https://", "http://127.0.0.1", "http://localhost"))):
        # Plain http is only accepted on loopback; across the tailnet it must be Tailscale HTTPS.
        return None
    token_raw = str(value.get("token_file") or "").strip()
    token_file = Path(os.path.expanduser(token_raw)) if token_raw else None
    return IdeasForwardConfig(url=url, token_file=token_file, dry_run=dry_run,
                              timeout_seconds=float(value.get("timeout_seconds") or 30.0))


def build_payload(records: Iterable[Any]) -> dict[str, Any]:
    items = list(records)
    if not items:
        raise ValueError("Empty ideas batch.")
    first = items[0]
    messages = []
    for item in items:
        media = []
        path = getattr(item, "media_path", None)
        if path is not None and Path(path).is_file():
            size = Path(path).stat().st_size
            if size <= MAX_MEDIA_BYTES:
                media.append({
                    "filename": Path(path).name,
                    "mime_type": mimetypes.guess_type(str(path))[0] or "application/octet-stream",
                    "base64": base64.b64encode(Path(path).read_bytes()).decode("ascii"),
                })
            else:
                media.append({"filename": Path(path).name, "omitted": f"{size} bytes > limit"})
        messages.append({
            "message_id": item.message_id,
            "received_at": item.received_at,
            "push_name": item.push_name,
            "kind": item.kind,
            # content already carries the local audio/video transcript or the caption.
            "text": item.content,
            "media": media,
        })
    return {
        "schema": SCHEMA,
        "source": "whatsapp-batata",
        "group_id": first.group_id,
        "group_subject": first.group_subject,
        "project": first.project,
        "messages": messages,
    }


def _post(config: IdeasForwardConfig, payload: dict[str, Any]) -> dict[str, Any]:
    token = config.token_file.read_text(encoding="utf-8").strip() if config.token_file else ""
    if not token:
        raise RuntimeError("Ideas pipeline token file is missing or empty.")
    request = urllib.request.Request(
        str(config.url),
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
            body = json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Ideas pipeline HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:300]}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Ideas pipeline unreachable: {exc}") from exc
    if not isinstance(body, dict) or body.get("ok") is not True or not body.get("id"):
        raise RuntimeError(f"Ideas pipeline rejected the batch: {str(body)[:300]}")
    return body


def _atomic_json(filename: Path, value: dict[str, Any]) -> None:
    tmp = filename.with_name(f".{filename.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(filename)


def forward_batch(records: list[Any], config: IdeasForwardConfig, *, data_dir: Path,
                  clock=time.time, post=_post) -> dict[str, Any] | None:
    """Forward one settled batch. Returns the receipt, or None while waiting to retry."""
    now = clock()
    for item in records:
        attempt = item.path / ATTEMPT_FILENAME
        try:
            last = json.loads(attempt.read_text(encoding="utf-8")).get("at_epoch", 0)
        except (OSError, json.JSONDecodeError, AttributeError):
            last = 0
        if now - float(last) < RETRY_SECONDS:
            return None
    payload = build_payload(records)
    for item in records:
        _atomic_json(item.path / ATTEMPT_FILENAME, {"at_epoch": now})
    if config.dry_run:
        outbox = data_dir / "ideas-forward" / "outbox"
        outbox.mkdir(parents=True, exist_ok=True)
        name = f"{int(now)}-{records[0].message_id}.json".replace("/", "_")
        _atomic_json(outbox / name, payload)
        receipt = {"ok": True, "id": None, "dry_run": True, "outbox_file": str(outbox / name)}
    else:
        receipt = post(config, payload)
    marker = {
        "version": 1,
        "mode": "ideas_forward",
        "idea_id": receipt.get("id"),
        "status": receipt.get("status"),
        "dry_run": config.dry_run,
        "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "source_message_ids": [item.message_id for item in records],
    }
    for item in records:
        _atomic_json(item.path / SUBMISSION_FILENAME, marker)
    return receipt
