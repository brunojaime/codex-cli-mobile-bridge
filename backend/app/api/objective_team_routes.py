from pathlib import Path
import os

from fastapi import APIRouter, Depends, HTTPException, Response

from backend.app.api.routes import get_container
from backend.app.application.services.objective_team_view import ObjectiveTeamView

router = APIRouter(prefix="/objective-team", tags=["objective-team"])


def get_view(container=Depends(get_container)):
    root = os.environ.get("NIENFOS_OBJECTIVE_STATE", str(Path.home() / ".local/state/nienfos-objective-team"))
    return ObjectiveTeamView(root, container.message_service.list_workspaces())


def read(call):
    try:
        return call()
    except (KeyError, FileNotFoundError):
        raise HTTPException(404, "No se encontró la ejecución o evidencia") from None
    except (OSError, ValueError, TypeError):
        raise HTTPException(503, "No se pudo leer el estado. Reintentá sin iniciar otra ejecución.") from None


@router.get("")
def overview(workspace_path: str | None = None, view=Depends(get_view)):
    return read(lambda: view.overview(workspace_path))


@router.get("/{run_id}")
def detail(run_id: str, view=Depends(get_view), container=Depends(get_container)):
    result = read(lambda: view.project(view.state(run_id)))
    result["can_open_chats"] = container.settings.bridge_environment == "prod"
    return result


@router.get("/{run_id}/images/{image_id}")
def image(run_id: str, image_id: str, view=Depends(get_view)):
    data, content_type = read(lambda: view.image(run_id, image_id))
    return Response(data, media_type=content_type, headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})
