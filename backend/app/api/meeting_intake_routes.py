from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from backend.app.api.routes import get_container
from backend.app.application.services.meeting_intake_service import (
    MeetingDecisionRequest, MeetingIntakeConflict, MeetingIntakeRequest, MeetingIntakeService,
)

router = APIRouter(prefix="/meeting-intakes", tags=["meeting-intakes"])


def _service(container):
    return MeetingIntakeService(
        container.message_service,
        Path(container.settings.chat_store_path).with_suffix(".meetings.sqlite3"),
    )


@router.post("/{delivery_key}/decision")
def decide_plan(delivery_key: str, payload: MeetingDecisionRequest, container=Depends(get_container)):
    try:
        return _service(container).decide(delivery_key, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MeetingIntakeConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("")
def launch_meeting(payload: MeetingIntakeRequest, container=Depends(get_container)):
    service = _service(container)
    try:
        return service.launch(payload)
    except MeetingIntakeConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
