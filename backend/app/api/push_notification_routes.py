"""No public send endpoint. Enrollment shares the existing private bridge boundary."""

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool
from uuid import UUID

from backend.app.api.project_secret_routes import SecretRoute
from backend.app.application.services.push_notification_service import (
    PushError,
    PushNotificationService,
)


def install_push_notifications(app, container):
    service = PushNotificationService(container.settings)
    app.state.push_notifications = service
    router = APIRouter(prefix="/notifications", route_class=SecretRoute)

    async def invoke(method, *args, **kwargs):
        try:
            return await run_in_threadpool(method, *args, **kwargs)
        except PushError as exc:
            raise HTTPException(exc.status, str(exc)) from None

    async def private(request: Request):
        if not service.trusted_network(
            request.client.host if request.client else "", request.headers.get("origin")
        ):
            raise HTTPException(
                403, "Esta operación requiere la conexión privada del bridge."
            )

    def bearer(request):
        header = request.headers.get("authorization", "")
        return header[7:] if header.startswith("Bearer ") else ""

    async def device(request: Request):
        return await invoke(service.authenticate, bearer(request))

    class Registration(BaseModel):
        model_config = ConfigDict(extra="forbid")
        installationId: UUID
        token: str = Field(min_length=32, max_length=4096, pattern=r"^[A-Za-z0-9_:-]+$")
        platform: str = Field(pattern=r"^android$")

    class Read(BaseModel):
        session_id: str = Field(min_length=1, max_length=200)
        whole_project: bool = False

    class Logo(BaseModel):
        session_id: str = Field(min_length=1, max_length=200)
        path: str = Field(min_length=1, max_length=1000)

    @router.get("/config", dependencies=[Depends(private)])
    async def config():
        result = {
            "configured": service.configured,
            "bridge_id": service.bridge_id,
            "environment": service.environment,
            "consent_required": True,
            "device_verification_required": True,
        }
        if service.configured:
            import json

            result["firebase_project_id"] = json.loads(service.credential)["project_id"]
        return result

    @router.post("/devices", dependencies=[Depends(private)])
    async def register(payload: Registration, request: Request):
        await invoke(service.limit, "register:" + request.client.host)
        return await invoke(
            service.register,
            str(payload.installationId),
            bearer(request),
            payload.token,
            payload.platform,
        )

    @router.get("/devices/me")
    async def status(current=Depends(device)):
        return {"enabled": True, "verified": bool(current["verified_at"])}

    @router.delete("/devices/me")
    async def revoke(current=Depends(device)):
        await invoke(service.revoke, current)
        return {"enabled": False}

    @router.post("/devices/me/test")
    async def test(current=Depends(device)):
        return await invoke(service.test, current)

    @router.post("/read")
    async def read(payload: Read, current=Depends(device)):
        await invoke(service.read, current, payload.session_id, payload.whole_project)
        return {"read": True}

    @router.get("/events/{event_id}")
    async def event(event_id: str, current=Depends(device)):
        return await invoke(service.event, current, event_id)

    @router.post("/events/{event_id}/receipt")
    async def receipt(event_id: str, current=Depends(device)):
        return await invoke(service.receipt, current, event_id)

    @router.get("/projects/{session_id}/logo", dependencies=[Depends(private)])
    async def logo(session_id: str):
        path = await invoke(service.logo, session_id)
        return FileResponse(
            path,
            headers={
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "private,max-age=300",
            },
        )

    @router.post("/projects/{session_id}/logo", dependencies=[Depends(private)])
    async def upload_logo(session_id: str, image: UploadFile = File(...)):
        try:
            data = await image.read(512 * 1024 + 1)
            return await invoke(service.upload_logo, session_id, data)
        finally:
            await image.close()

    @router.put("/projects/logo", dependencies=[Depends(private)])
    async def set_logo(payload: Logo):
        return await invoke(service.set_logo, payload.session_id, payload.path)

    app.include_router(router)
    app.include_router(router, prefix="/api/v1")

    @app.on_event("startup")
    async def start():
        try:
            await run_in_threadpool(service.start)
        except Exception:
            # Keep the chat usable; /config and opt-in expose retryable failures.
            import logging

            logging.getLogger(__name__).error(
                "Push worker unavailable; device activation can retry."
            )

    @app.on_event("shutdown")
    async def stop():
        await run_in_threadpool(service.close)
