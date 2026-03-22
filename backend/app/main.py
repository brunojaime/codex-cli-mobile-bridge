from __future__ import annotations

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes import get_container, router
from backend.app.container import AppContainer, build_container
from backend.app.infrastructure.config.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    container = build_container(settings)
    app = FastAPI(title=container.settings.app_name)
    _configure_dependencies(app, container)
    _configure_middleware(app, container)
    app.include_router(router)
    return app


def run() -> None:
    settings = Settings()
    uvicorn.run(
        "backend.app.main:create_app",
        factory=True,
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )


def _configure_dependencies(app: FastAPI, container: AppContainer) -> None:
    app.dependency_overrides[get_container] = lambda: container


def _configure_middleware(app: FastAPI, container: AppContainer) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=container.settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
