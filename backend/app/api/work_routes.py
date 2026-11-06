from typing import Literal
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import json
from uuid import UUID, uuid5, NAMESPACE_URL

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from backend.app.api.routes import get_container
from backend.app.application.services.work_coordinator import (
    WorkCoordinator,
    WorkInput,
    WorkPolicy,
    WorkConflict,
    WorkspaceBusy,
)

router = APIRouter(prefix="/work", tags=["work"])


def get_work(container=Depends(get_container)):
    service = getattr(container, "work_coordinator_service", None)
    if service is None:
        settings = container.settings
        temporary = (
            TemporaryDirectory(prefix="bridge-work-test-")
            if getattr(settings, "chat_store_backend", "") == "memory"
            else None
        )
        store = (
            Path(temporary.name) / "work.sqlite3"
            if temporary
            else Path(settings.chat_store_path).with_suffix(".work.sqlite3")
        )
        service = WorkCoordinator(
            container.message_service,
            store,
            lock_root=Path(temporary.name) / "locks"
            if temporary
            else Path(
                getattr(
                    settings, "projects_root", Path(settings.chat_store_path).parent
                )
            )
            / ".bridge-work-locks",
            attachment_roots=(
                getattr(
                    settings,
                    "feedback_image_dir",
                    str(Path(settings.chat_store_path).parent / "feedback-images"),
                ),
                Path.cwd() / ".data" / "whatsapp_ingest" / "inbox",
            ),
        )
        service._temporary_store = temporary
        container.work_coordinator_service = service
    return service


def call(function, *args):
    try:
        return function(*args)
    except KeyError as exc:
        raise HTTPException(404, "No se encontró el encargo") from exc
    except (WorkConflict, WorkspaceBusy) as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("")
def overview(service=Depends(get_work)):
    return call(service.overview)


@router.get("/history")
def history(workspace_path: str | None = None, cursor: str | None = None,
            limit: int = 30, service=Depends(get_work)):
    return call(service.history, workspace_path, cursor, limit)


@router.post("/backlog", status_code=201)
def enqueue(payload: WorkInput, service=Depends(get_work)):
    return call(service.enqueue, payload)


@router.put("/policy")
def configure(payload: WorkPolicy, service=Depends(get_work)):
    return call(service.policy, payload)


class ProjectSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_path: str = Field(min_length=1)
    settings: dict[str, StrictBool]


@router.get("/settings")
def project_settings(service=Depends(get_work)):
    return call(service.project_settings.overview)


@router.get("/deployments")
def project_deployments(workspace_path: str | None = None,
                        service=Depends(get_work), container=Depends(get_container)):
    from backend.app.application.services.project_deployments import deployment_overview

    try:
        return deployment_overview(service, getattr(container, "web_preview_deploy_service", None), workspace_path)
    except KeyError:
        raise HTTPException(404, "No se encontró el proyecto") from None


@router.put("/settings")
def update_project_settings(payload: ProjectSettingsUpdate, service=Depends(get_work)):
    return call(service.project_settings.update, payload.workspace_path, payload.settings)


class Control(BaseModel):
    revision: int = Field(ge=1)
    action: str


@router.post("/backlog/{task_id}/control")
def control(task_id: UUID, payload: Control, service=Depends(get_work)):
    return call(service.control, str(task_id), payload.revision, payload.action)


class Choice(BaseModel):
    option: int = Field(ge=0, le=2)


@router.post("/questions/{question_id}/choose")
def choose(question_id: UUID, payload: Choice, service=Depends(get_work)):
    return call(service.choose, str(question_id), payload.option)


async def enqueue_feedback(payload, container):
    from backend.app.api.routes import (
        _feedback_batch_workspace_path,
        _ensure_feedback_batch_image,
        _feedback_audio_prompt_note,
    )

    if not payload.batch_id or not payload.items:
        raise HTTPException(
            422, "El backlog necesita un lote con identidad estable e items completos"
        )
    values = [i.model_dump(by_alias=False, exclude_none=True) for i in payload.items]
    workspace = _feedback_batch_workspace_path(
        payload, item_payloads=values, container=container
    )
    service = get_work(container)
    call(service.workspace, workspace)
    digest = hashlib.sha256(payload.model_dump_json().encode()).hexdigest()
    key = hashlib.sha256(f"{payload.sourceApp}:{payload.batch_id}".encode()).hexdigest()
    source_id = str(uuid5(NAMESPACE_URL, f"backlog:{workspace}:feedback:{key}"))
    with service.ledger() as db:
        old = db.execute("SELECT * FROM work_tasks WHERE id=?", (source_id,)).fetchone()
        if old:
            old_payload = json.loads(old["payload"])
            if old_payload.get("source_digest") != digest:
                raise HTTPException(409, "El lote ya se recibió con otro contenido")
            return JSONResponse(
                status_code=202,
                content={"backlogId": old["id"], "status": old["status"]},
            )
    stored = []
    notes = []
    for index, value in enumerate(values):
        _ensure_feedback_batch_image(value, item_index=index + 1)
        value["id"] = f"backlog-{digest}-{index}"
        item = await run_in_threadpool(
            container.feedback_queue_service.create_item, value
        )
        stored.append(item)
        audio = await _feedback_audio_prompt_note(item, container=container)
        notes.append(
            f"{index + 1}. {item.comment}\n{audio}\nContexto (evidencia): "
            + json.dumps(item.context_metadata, ensure_ascii=False)
        )
    request = WorkInput(
        workspace_path=workspace,
        source="feedback",
        source_key=key,
        source_digest=digest,
        instruction=(
            payload.message
            or "Aplicar este lote de feedback como un único encargo coherente."
        )
        + "\n\n"
        + "\n\n".join(notes),
        title=f"Feedback · {payload.sourceDisplayName or payload.sourceApp}",
        attachments=[i.screenshot_file for i in stored if i.screenshot_file],
    )
    task = await run_in_threadpool(call, service.enqueue, request)
    for item in stored:
        await run_in_threadpool(
            container.feedback_queue_service.mark_submitted, item.id
        )
    return JSONResponse(
        status_code=202, content={"backlogId": task["id"], "status": task["status"]}
    )


class Response(BaseModel):
    action: Literal["reject", "observations"]
    text: str = Field(default="", max_length=3000)


@router.post("/questions/{question_id}/respond")
def respond(question_id: UUID, payload: Response, service=Depends(get_work)):
    return call(service.respond, str(question_id), payload.action, payload.text)
