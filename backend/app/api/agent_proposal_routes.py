from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.app.api.routes import get_container
from backend.app.application.services.agent_proposal_service import (
    AgentProposalService,
    ProposalConflict,
    ProposalDecision,
    ProposalDraft,
    ProposalMissing,
    ProposalRevision,
)

router = APIRouter(prefix="/agent-proposals", tags=["agent-proposals"])


def service(container=Depends(get_container)):
    return AgentProposalService(
        container.message_service,
        Path(container.settings.chat_store_path).with_suffix(".proposals.sqlite3"),
    )


def invoke(function, *args):
    try:
        return function(*args)
    except ProposalMissing as exc:
        raise HTTPException(404, str(exc)) from exc
    except ProposalConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("")
def list_proposals(
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    svc=Depends(service),
):
    return invoke(svc.list, limit, offset)


@router.post("", status_code=201)
def create_proposal(payload: ProposalDraft, svc=Depends(service)):
    return invoke(svc.create, payload)


@router.get("/{proposal_id}")
def get_proposal(proposal_id: UUID, svc=Depends(service)):
    return invoke(svc.get, str(proposal_id))


@router.put("/{proposal_id}")
def revise_proposal(proposal_id: UUID, payload: ProposalRevision, svc=Depends(service)):
    return invoke(svc.revise, str(proposal_id), payload)


class ReadProposal(BaseModel):
    revision: int = Field(ge=1, strict=True)


@router.post("/{proposal_id}/read")
def read_proposal(proposal_id: UUID, payload: ReadProposal, svc=Depends(service)):
    return invoke(svc.read, str(proposal_id), payload.revision)


@router.post("/{proposal_id}/decisions")
def decide_proposal(proposal_id: UUID, payload: ProposalDecision, svc=Depends(service)):
    return invoke(svc.decide, str(proposal_id), payload)
