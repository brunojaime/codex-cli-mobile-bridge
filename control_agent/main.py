from __future__ import annotations

import hmac
from typing import Literal

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from control_agent.config import ControlSettings
from control_agent.service import ControlService


class RestartRequest(BaseModel):
    mode: Literal["graceful", "force"] = "graceful"


def create_app(
    settings: ControlSettings | None = None,
    service: ControlService | None = None,
) -> FastAPI:
    resolved_settings = settings or ControlSettings.from_env()
    resolved_service = service or ControlService(resolved_settings)
    app = FastAPI(title="Codex Mobile Control Agent")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    def require_token(authorization: str | None = Header(default=None)) -> None:
        expected = f"Bearer {resolved_settings.token}"
        if authorization is None or not hmac.compare_digest(authorization, expected):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "invalid_control_token", "message": "Invalid token."},
            )

    @app.get("/health")
    def health(_auth: None = Depends(require_token)) -> dict[str, object]:
        return {
            "status": "ok",
            "service": "codex-mobile-control",
            "environment_count": len(resolved_settings.environments),
        }

    @app.get("/environments")
    def environments(_auth: None = Depends(require_token)) -> dict[str, object]:
        return {
            "environments": resolved_service.list_environment_statuses(),
            "codex": resolved_service.codex_status(),
        }

    @app.post("/environments/{environment_name}/restart", status_code=202)
    def restart_environment(
        environment_name: str,
        payload: RestartRequest,
        _auth: None = Depends(require_token),
    ) -> dict[str, object]:
        try:
            action = resolved_service.submit_restart(environment_name, payload.mode)
        except KeyError:
            raise HTTPException(
                status_code=404,
                detail={"code": "unknown_environment"},
            ) from None
        except RuntimeError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "restart_already_active", "message": str(exc)},
            ) from exc
        return action.as_dict()

    @app.get("/actions/{action_id}")
    def action(action_id: str, _auth: None = Depends(require_token)) -> dict[str, object]:
        try:
            return resolved_service.action(action_id).as_dict()
        except KeyError:
            raise HTTPException(
                status_code=404,
                detail={"code": "unknown_action"},
            ) from None

    return app


def run() -> None:
    settings = ControlSettings.from_env()
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
    )


if __name__ == "__main__":
    run()
