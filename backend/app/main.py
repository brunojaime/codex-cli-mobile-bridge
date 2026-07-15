from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import datetime, timezone
import sqlite3
import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes import ensure_dev_stage_chat_run, get_container, router
from backend.app.application.services.message_service import MaintenanceModeError
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
    _configure_background_workers(app, container)
    app.include_router(router)
    app.include_router(router, prefix="/api/v1")
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
    @app.exception_handler(MaintenanceModeError)
    async def handle_maintenance_mode_error(  # type: ignore[unused-ignore]
        _request,
        exc: MaintenanceModeError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={
                "detail": {
                    "error": "backend_drain_active",
                    "code": "backend_drain_active",
                    "message": str(exc),
                }
            },
        )

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


def _configure_background_workers(app: FastAPI, container: AppContainer) -> None:
    runner_task: asyncio.Task[None] | None = None

    @app.on_event("startup")
    async def start_dev_pipeline_auto_runner() -> None:
        nonlocal runner_task
        settings = container.settings
        if (
            settings.bridge_environment != "dev"
            or not settings.dev_pipeline_enabled
            or not settings.dev_pipeline_auto_runner_enabled
        ):
            return
        runner_task = asyncio.create_task(
            _dev_pipeline_auto_runner_loop(container),
            name="dev-pipeline-auto-runner",
        )

    @app.on_event("shutdown")
    async def stop_dev_pipeline_auto_runner() -> None:
        if runner_task is None:
            return
        runner_task.cancel()
        with suppress(asyncio.CancelledError):
            await runner_task


async def _dev_pipeline_auto_runner_loop(container: AppContainer) -> None:
    settings = container.settings
    interval = settings.dev_pipeline_auto_runner_interval_seconds
    worker_id = settings.dev_pipeline_auto_runner_worker_id
    started_at = None
    if not settings.dev_pipeline_auto_runner_reconcile_existing:
        started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    while True:
        try:
            await asyncio.to_thread(
                _auto_materialize_and_start_stage_runs,
                container,
                worker_id,
                started_at,
            )
        except Exception:
            # Reconciliation must stay alive. Failures are represented in the
            # DEV pipeline state when materialization itself blocks.
            pass
        await asyncio.sleep(interval)


def _auto_materialize_and_start_stage_runs(
    container: AppContainer,
    worker_id: str,
    created_after: str | None,
) -> None:
    results = container.dev_pipeline_service.auto_materialize_queued_backlog(
        worker_id=worker_id,
        limit=1,
        created_after=created_after,
    )
    for result in results:
        stage = result.get("stage") if isinstance(result, dict) else None
        if not isinstance(stage, dict) or not stage.get("stage_id"):
            continue
        ensure_dev_stage_chat_run(
            container,
            stage_id=str(stage["stage_id"]),
            requested_by=worker_id,
        )
