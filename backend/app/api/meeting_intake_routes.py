from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from backend.app.api.routes import get_container
from backend.app.application.services.meeting_intake_service import (
    MeetingIntakeConflict, MeetingIntakeRequest, MeetingIntakeService,
)

router = APIRouter(prefix="/meeting-intakes", tags=["meeting-intakes"])


@router.post("")
def launch_meeting(payload: MeetingIntakeRequest, container=Depends(get_container)):
    service = MeetingIntakeService(
        container.message_service,
        Path(container.settings.chat_store_path).with_suffix(".meetings.sqlite3"),
    )
    try:
        return service.launch(payload)
    except MeetingIntakeConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
