"""Renew the operator's configured read-only Drive authorization via local OAuth.

Uses the existing OAuth client and token path. Never prints codes or credentials.
The consent URL is kept in private state for opening in Batata's own browser.
"""
from __future__ import annotations

import base64
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import secrets
import sys
import time
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.relevamientos.core import atomic  # noqa: E402


def main():
    os.umask(0o077)
    load_dotenv(ROOT / ".env", override=False)
    load_dotenv(ROOT / ".data/relevamientos-inbox/service.env", override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", default=os.environ.get("RELEVAMIENTOS_GOOGLE_ACCOUNT"))
    args = parser.parse_args()
    token_file = os.environ.get("RELEVAMIENTOS_GOOGLE_TOKEN_FILE") or os.environ.get("GOOGLE_DRIVE_TOKEN_FILE")
    client_file = os.environ.get("GOOGLE_DRIVE_OAUTH_CLIENT_FILE")
    if not token_file or not client_file:
        raise ValueError("existing_drive_oauth_configuration_required")
    destination = Path(token_file).expanduser()
    config = json.loads(Path(client_file).expanduser().read_text())["installed"]
    previous = json.loads(destination.read_text()) if destination.exists() else {}
    directory = ROOT / ".data/relevamientos-inbox"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    result = {"state": "waiting_for_google_authorization"}

    class Callback(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Callback URLs contain an authorization code.

        def do_GET(self):
            params = parse_qs(urlparse(self.path).query)
            if not secrets.compare_digest(params.get("state", [""])[0], state):
                self.send_error(400, "Invalid authorization state")
                return
            if params.get("error") or not params.get("code"):
                result["state"] = "authorization_denied"
                self.send_error(400, "Google authorization was not completed")
                return
            try:
                response = httpx.post("https://oauth2.googleapis.com/token", data={
                    "client_id": config["client_id"], "client_secret": config["client_secret"],
                    "grant_type": "authorization_code", "code": params["code"][0],
                    "code_verifier": verifier, "redirect_uri": redirect,
                }, timeout=30)
                response.raise_for_status()
                value = response.json()
                if not value.get("refresh_token"):
                    raise ValueError("refresh_token_missing")
                identity = httpx.get("https://www.googleapis.com/drive/v3/about",
                                     params={"fields": "user(emailAddress)"},
                                     headers={"Authorization": "Bearer " + value["access_token"]}, timeout=30)
                identity.raise_for_status()
                account = identity.json()["user"]["emailAddress"]
                if args.account and account.casefold() != args.account.casefold():
                    raise ValueError("authorized_account_does_not_match_requested_account")
                saved = {**previous, "client_id": config["client_id"],
                         "account": account,
                         "client_secret": config["client_secret"],
                         "refresh_token": value["refresh_token"], "token": value["access_token"],
                         "token_uri": "https://oauth2.googleapis.com/token",
                         "scopes": value.get("scope", "https://www.googleapis.com/auth/drive.readonly").split(),
                         "expiry": (datetime.now(timezone.utc) + timedelta(seconds=value.get("expires_in", 3600))).isoformat()}
                atomic(destination, saved)
                result["state"] = "authorization_complete"
                body = "Drive autorizado para el monitor de relevamientos. Podés cerrar esta pestaña.".encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as error:
                result.update(state="authorization_failed", error_type=type(error).__name__)
                self.send_error(502, "Authorization failed; details suppressed")

    server = HTTPServer(("127.0.0.1", 0), Callback)
    server.timeout = 5
    redirect = f"http://127.0.0.1:{server.server_port}/callback"
    params = {"client_id": config["client_id"], "redirect_uri": redirect,
              "response_type": "code", "scope": "https://www.googleapis.com/auth/drive.readonly",
              "access_type": "offline", "prompt": "consent", "state": state,
              "code_challenge": challenge, "code_challenge_method": "S256"}
    if args.account or previous.get("account"):
        params["login_hint"] = args.account or previous["account"]
    pending = directory / "oauth-pending.json"
    atomic(pending, {"url": "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)})
    atomic(directory / "oauth-status.json", result)
    print(json.dumps(result), flush=True)
    deadline = time.monotonic() + 1800
    try:
        while result["state"] == "waiting_for_google_authorization" and time.monotonic() < deadline:
            server.handle_request()
        if result["state"] == "waiting_for_google_authorization":
            result["state"] = "authorization_timed_out"
    finally:
        server.server_close()
        pending.unlink(missing_ok=True)
        atomic(directory / "oauth-status.json", result)
    print(json.dumps(result), flush=True)
    return 0 if result["state"] == "authorization_complete" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({"state": "authorization_failed", "error_type": type(error).__name__}))
        raise SystemExit(1) from None
