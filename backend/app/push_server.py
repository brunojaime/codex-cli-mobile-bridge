"""Notification-only companion: shares the real chat DB without restarting Codex jobs."""

from __future__ import annotations
import argparse
from pathlib import Path
from types import SimpleNamespace
from fastapi import FastAPI
import uvicorn
from backend.app.api.push_notification_routes import install_push_notifications
from backend.app.infrastructure.config.settings import Settings


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", choices=["prod", "dev"], required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--secrets-file", required=True)
    parser.add_argument("--node", required=True)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    if not Path(args.database).is_file():
        raise SystemExit("The existing real chat database is required.")
    settings = Settings(
        _env_file=args.secrets_file,
        bridge_environment=args.environment,
        chat_store_path=str(Path(args.database).resolve()),
        chat_store_backend="sqlite",
        push_node_binary=args.node,
    )
    app = FastAPI(title="Codex Mobile notifications")
    install_push_notifications(app, SimpleNamespace(settings=settings))

    @app.get("/health")
    def health():
        service = app.state.push_notifications
        return {
            "status": "ok",
            "environment": args.environment,
            "configured": service.configured,
            "bridge_id": service.bridge_id,
            "service": "notifications",
        }

    uvicorn.run(
        app, host="0.0.0.0", port=args.port, access_log=False, proxy_headers=False
    )


if __name__ == "__main__":
    run()
