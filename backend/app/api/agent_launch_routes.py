from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from backend.app.api.routes import get_container
from backend.app.application.services.generator_reviewer_launch_service import (
    GeneratorReviewerLaunch,
    GeneratorReviewerLaunchService,
    LaunchConflict,
)

router = APIRouter(prefix="/agent-launches", tags=["agent-launches"])


def launch_service(container):
    path = Path(container.settings.chat_store_path).with_suffix(".launches.sqlite3")
    return GeneratorReviewerLaunchService(container.message_service, path)


@router.post("/generator-reviewer")
def launch_generator_reviewer(
    payload: GeneratorReviewerLaunch, container=Depends(get_container)
):
    try:
        return launch_service(container).launch(payload)
    except LaunchConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{launch_id}")
def get_agent_launch(launch_id: UUID, container=Depends(get_container)):
    result = launch_service(container).get(str(launch_id))
    if result is None:
        raise HTTPException(status_code=404, detail="Lanzamiento no encontrado")
    return result
