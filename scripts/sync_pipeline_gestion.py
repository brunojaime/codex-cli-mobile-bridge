#!/usr/bin/env python3
"""Send one prepared observation to Gestión DEV's authenticated canonical API.

No production origin, direct SQL or automatic commercial state transition.
Requires GESTION_PIPELINE_TOKEN from the environment/Secrets. Does not print it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit
import urllib.request

from dotenv import dotenv_values

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.application.services.jev_advisor import _NoRedirect
from scripts.environment_guard import (
    audit_event,
    decide,
    default_audit_log,
    resolve_current_environment,
)


def sync(payload: dict, *, origin: str, token: str) -> dict:
    parsed = urlsplit(origin)
    if (
        parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise ValueError("Use the exact DEV origin")
    if not (
        (parsed.scheme == "https" and parsed.netloc == "dev.gestion.nienfos.com")
        or (
            parsed.scheme == "http"
            and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        )
    ):
        raise ValueError("Only Gestión DEV or an isolated local instance is supported")
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def call(tool, arguments):
        body_bytes = json.dumps({"tool": tool, "arguments": arguments}).encode()
        if len(body_bytes) > 16_384:
            raise ValueError(
                "Agent API limit is 16 KiB; import larger observations through the project screen"
            )
        req = urllib.request.Request(
            origin.rstrip("/") + "/api/v1/agent/tools",
            data=body_bytes,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + token,
                "Idempotency-Key": "pipeline-" + digest,
            },
            method="POST",
        )
        with urllib.request.build_opener(_NoRedirect()).open(
            req, timeout=15
        ) as response:
            body = json.loads(response.read(1_000_000))
        envelope = body["data"]
        if envelope["environment"] != "development":
            raise ValueError("Wrong target environment")
        return envelope["result"]

    # Canonical state is read before and after writes.
    call("pipeline.evidence.list", {"projectId": payload["projectId"]})
    result = call("pipeline.evidence.import", payload)
    observed = call("pipeline.evidence.list", {"projectId": payload["projectId"]})
    if not any(x["id"] == result["observationId"] for x in observed["observations"]):
        raise ValueError("Imported observation was not found in the canonical read")
    return {
        "verified_import": True,
        "observation_id": result["observationId"],
        "commercial_state_changed": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("payload", type=Path)
    parser.add_argument("--origin", default="https://dev.gestion.nienfos.com")
    parser.add_argument("--send", action="store_true")
    args = parser.parse_args()
    payload = json.loads(args.payload.read_text())
    if not args.send:
        print(
            json.dumps(
                {
                    "mode": "plan",
                    "project_id": payload["projectId"],
                    "packet_id": payload["observation"]["packet_id"],
                    "next_action": "Run with --send after the DEV receiver is deployed and GESTION_PIPELINE_TOKEN is configured in Secrets.",
                }
            )
        )
        return 0
    values = dotenv_values(Path(__file__).resolve().parents[1] / ".env")
    token = os.environ.get("GESTION_PIPELINE_TOKEN") or values.get(
        "GESTION_PIPELINE_TOKEN"
    )
    if not token:
        print('{"error":"GESTION_PIPELINE_TOKEN_missing"}', file=sys.stderr)
        return 2
    decision = decide(
        current_environment=resolve_current_environment(), target_environment="dev"
    )
    audit_event(
        operation="pipeline_gestion_sync",
        action="write",
        decision=decision,
        audit_log=default_audit_log(),
    )
    if not decision.allowed:
        print('{"error":"environment_boundary_violation"}', file=sys.stderr)
        return 2
    try:
        print(json.dumps(sync(payload, origin=args.origin, token=token)))
        return 0
    except Exception:
        print(
            '{"error":"gestion_sync_not_confirmed","retry":"Reuse the same payload; imports are idempotent."}',
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
