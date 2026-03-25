from __future__ import annotations

import sqlite3
import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes import get_container, router
from backend.app.container import AppContainer, build_container
from backend.app.infrastructure.config.settings import Settings
from backend.app.domain.repositories.chat_repository import PersistenceDataError
from backend.app.domain.repositories.chat_repository import PersistenceUnavailableError


def create_app(settings: Settings | None = None) -> FastAPI:
    container = build_container(settings)
    app = FastAPI(title=container.settings.app_name)
    _configure_dependencies(app, container)
    _configure_middleware(app, container)
    _configure_exception_handlers(app)
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


def _configure_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(sqlite3.DatabaseError)
    async def handle_sqlite_database_error(  # type: ignore[unused-ignore]
        _request,
        exc: sqlite3.DatabaseError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={
                "detail": {
                    "error": "sqlite_database_error",
                    "code": "sqlite_database_error",
                    "message": str(exc),
                }
            },
        )

    @app.exception_handler(PersistenceDataError)
    async def handle_persistence_data_error(  # type: ignore[unused-ignore]
        _request,
        exc: PersistenceDataError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={
                "detail": {
                    "error": "persistence_data_error",
                    "table": exc.table,
                    "row_id": exc.row_id,
                    "field": exc.field,
                    "code": exc.code,
                    "message": exc.detail,
                }
            },
        )

    @app.exception_handler(PersistenceUnavailableError)
    async def handle_persistence_unavailable_error(  # type: ignore[unused-ignore]
        _request,
        exc: PersistenceUnavailableError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={
                "detail": {
                    "error": "persistence_unavailable",
                    "table": exc.issue.table,
                    "row_id": exc.issue.row_id,
                    "field": exc.issue.field,
                    "code": exc.issue.code,
                    "message": exc.issue.detail,
                }
            },
        )
