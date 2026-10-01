"""Write-only secret endpoints; validation must never echo submitted values."""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from backend.app.api.schemas import ProjectSecretUpsertRequest, ProjectSecretsResponse
from backend.app.application.services.project_secret_service import (
    ProjectSecretError,
    ProjectSecretWorkspaceError,
)
from backend.app.container import AppContainer


class SecretRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def sanitized(request):
            try:
                return await handler(request)
            except RequestValidationError:
                raise HTTPException(422, "Invalid secret request. Check the name and value.") from None

        return sanitized


class SecretUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_path: str = Field(..., min_length=1, max_length=2000)
    name: str = Field(..., min_length=1, max_length=256)
    new_name: str = Field(..., min_length=1, max_length=256, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    value: str | None = Field(default=None, min_length=1, max_length=65536)


def build_secret_router(container_dependency) -> APIRouter:
    router = APIRouter(route_class=SecretRoute)

    async def invoke(method, **kwargs):
        try:
            return await run_in_threadpool(method, **kwargs)
        except ProjectSecretWorkspaceError as exc:
            raise HTTPException(403, str(exc)) from exc
        except ProjectSecretError as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.get("/project-secrets", response_model=ProjectSecretsResponse)
    async def list_secrets(
        workspace_path: str = Query(..., min_length=1, max_length=2000),
        container: AppContainer = Depends(container_dependency),
    ):
        return await invoke(container.project_secret_service.list_secret_names,
                            workspace_path=workspace_path)

    @router.post("/project-secrets", response_model=ProjectSecretsResponse)
    async def set_secret(
        payload: ProjectSecretUpsertRequest,
        container: AppContainer = Depends(container_dependency),
    ):
        return await invoke(container.project_secret_service.set_secret, **payload.model_dump())

    @router.patch("/project-secrets", response_model=ProjectSecretsResponse)
    async def update_secret(
        payload: SecretUpdateRequest,
        container: AppContainer = Depends(container_dependency),
    ):
        return await invoke(container.project_secret_service.update_secret, **payload.model_dump())

    @router.delete("/project-secrets", response_model=ProjectSecretsResponse)
    async def delete_secret(
        workspace_path: str = Query(..., min_length=1, max_length=2000),
        name: str = Query(..., min_length=1, max_length=256),
        container: AppContainer = Depends(container_dependency),
    ):
        return await invoke(container.project_secret_service.delete_secret,
                            workspace_path=workspace_path, name=name)

    return router
