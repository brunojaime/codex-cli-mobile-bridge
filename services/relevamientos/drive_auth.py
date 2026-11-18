"""Reuse operator-configured Google OAuth without copying or displaying secrets."""
from __future__ import annotations

import json
import os
from pathlib import Path

SECRET_NAMES = (
    "RELEVAMIENTOS_GOOGLE_CLIENT_ID",
    "RELEVAMIENTOS_GOOGLE_CLIENT_SECRET",
    "RELEVAMIENTOS_GOOGLE_REFRESH_TOKEN",
)


def credentials(environ=None):
    env = os.environ if environ is None else environ
    if all(env.get(name) for name in SECRET_NAMES):
        return {"client_id": env[SECRET_NAMES[0]], "client_secret": env[SECRET_NAMES[1]],
                "refresh_token": env[SECRET_NAMES[2]], "grant_type": "refresh_token"}, "environment"
    # Only an explicit operator-configured token file is used. Never inspect
    # ChatGPT connector storage or borrow its internal credentials.
    filename = env.get("RELEVAMIENTOS_GOOGLE_TOKEN_FILE") or env.get("GOOGLE_DRIVE_TOKEN_FILE")
    if filename:
        try:
            value = json.loads(Path(filename).expanduser().read_text())
        except (OSError, ValueError):
            raise ValueError("google_token_file_unreadable") from None
        if not isinstance(value, dict) or not all(
            isinstance(value.get(key), str) and value[key].strip()
            for key in ("client_id", "client_secret", "refresh_token")
        ):
            raise ValueError("google_token_file_not_refreshable")
        return {key: value[key] for key in ("client_id", "client_secret", "refresh_token")} | {
            "grant_type": "refresh_token"
        }, "configured_token_file"
    raise ValueError("google_oauth_not_configured")


def auth_status(environ=None):
    try:
        _, source = credentials(environ)
        return {"ready": True, "source": source, "missing_secret_names": []}
    except ValueError as exc:
        env = os.environ if environ is None else environ
        return {"ready": False, "problem": str(exc),
                "missing_secret_names": [name for name in SECRET_NAMES if not env.get(name)]}
