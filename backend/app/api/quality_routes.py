"""Internal DEV quality API. No route accepts externally asserted test results."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from backend.app.api.routes import get_container
from backend.app.container import AppContainer
from backend.app.application.services.pipeline_quality_service import (
    PipelineQualityService,
    QualityError,
)
from backend.app.domain.entities.pipeline_quality import QualityContract
from backend.app.domain.entities.feedback_validation import FeedbackValidationPlan
from backend.app.domain.entities.requirement_validation import (
    RequirementDefinition,
    RequirementFromSource,
    RequirementRevision,
    ManualAcceptanceReview,
)

router = APIRouter(prefix="/pipeline-quality", tags=["pipeline-quality"])


def quality(container: AppContainer = Depends(get_container)) -> PipelineQualityService:
    if container.settings.bridge_environment != "dev":
        raise HTTPException(403, "Quality operations belong to the DEV bridge")
    if container.pipeline_quality_service is None:
        raise HTTPException(409, "Pipeline quality is disabled")
    return container.pipeline_quality_service


class PacketRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace: str = Field(min_length=1, max_length=2000)
    work_item_id: str = Field(min_length=1, max_length=200)
    contract: QualityContract | None = None
    links: dict[str, str] = Field(default_factory=dict, max_length=10)


class RequirementRequest(RequirementDefinition):
    workspace: str = Field(min_length=1, max_length=2000)


class ExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attempt_key: str = Field(min_length=1, max_length=160)
    check_ids: list[str] | None = Field(default=None, max_length=60)


class LessonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    failed_receipt_id: str
    passed_receipt_id: str
    symptom: str = Field(min_length=1, max_length=4000)
    cause_hypothesis: str = Field(min_length=1, max_length=4000)
    resolution: str = Field(min_length=1, max_length=4000)
    conditions: str = Field(min_length=1, max_length=4000)


async def call(fn, *args, **kwargs) -> Any:
    try:
        return await run_in_threadpool(fn, *args, **kwargs)
    except (QualityError, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/packets")
async def packets(service: PipelineQualityService = Depends(quality)):
    return await call(service.packets)


@router.post("/packets")
async def register(
    payload: PacketRequest, service: PipelineQualityService = Depends(quality)
):
    args = {
        "workspace": payload.workspace,
        "work_item_id": payload.work_item_id,
        "links": payload.links,
    }
    if payload.contract:
        return await call(
            service.register, **args, contract=payload.contract.model_dump()
        )
    return await call(service.register_file, **args)


@router.get("/packets/{packet_id}")
async def status(packet_id: str, service: PipelineQualityService = Depends(quality)):
    return await call(service.status, packet_id)


@router.post("/packets/{packet_id}/execute")
async def execute(
    packet_id: str,
    payload: ExecuteRequest,
    service: PipelineQualityService = Depends(quality),
):
    return await call(service.execute, packet_id, **payload.model_dump())


@router.get("/packets/{packet_id}/diagnosis")
async def diagnosis(packet_id: str, service: PipelineQualityService = Depends(quality)):
    return await call(service.diagnose, packet_id)


@router.post("/packets/{packet_id}/close")
async def close(packet_id: str, service: PipelineQualityService = Depends(quality)):
    return await call(service.close, packet_id)


@router.get("/packets/{packet_id}/lessons")
async def lessons(packet_id: str, service: PipelineQualityService = Depends(quality)):
    return await call(service.lessons_for, packet_id)


@router.post("/packets/{packet_id}/lessons")
async def save_lesson(
    packet_id: str,
    payload: LessonRequest,
    service: PipelineQualityService = Depends(quality),
):
    return await call(service.save_lesson, packet_id=packet_id, **payload.model_dump())


@router.get("/export")
async def export(
    after: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    service: PipelineQualityService = Depends(quality),
):
    return await call(service.export, after=after, limit=limit)


@router.get("/feedback")
async def feedback_requests(
    workspace: str, service: PipelineQualityService = Depends(quality)
):
    return await call(service.feedback_requests, workspace)


@router.post("/requirements")
async def register_requirement(
    payload: RequirementRequest, service: PipelineQualityService = Depends(quality)
):
    return await call(
        service.register_requirement,
        workspace=payload.workspace,
        definition=payload.model_dump(exclude={"workspace"}),
    )


@router.get("/requirements")
async def requirements(
    workspace: str, service: PipelineQualityService = Depends(quality)
):
    return await call(service.requirements, workspace)


@router.get("/sources")
async def sources(workspace: str, service: PipelineQualityService = Depends(quality)):
    return await call(service.requirement_sources, workspace)


@router.post("/sources/{source_id}/requirements")
async def requirement_from_source(
    source_id: str,
    payload: RequirementFromSource,
    service: PipelineQualityService = Depends(quality),
):
    return await call(service.requirement_from_source, source_id, payload.model_dump())


@router.post("/requirements/{request_id}/revise")
async def revise_requirement(
    request_id: str,
    payload: RequirementRevision,
    service: PipelineQualityService = Depends(quality),
):
    return await call(service.revise_requirement, request_id, payload.model_dump())


@router.post("/requests/{request_id}/manual-review")
async def manual_review(
    request_id: str,
    payload: ManualAcceptanceReview,
    service: PipelineQualityService = Depends(quality),
):
    return await call(service.record_manual_review, request_id, payload.model_dump())


@router.get("/requests/{request_id}/history")
async def acceptance_history(
    request_id: str, service: PipelineQualityService = Depends(quality)
):
    return await call(service.acceptance_history, request_id)


@router.put("/feedback/{request_id}/plan")
@router.put("/requests/{request_id}/plan")
async def feedback_plan(
    request_id: str,
    payload: FeedbackValidationPlan,
    service: PipelineQualityService = Depends(quality),
):
    return await call(service.bind_feedback_plan, request_id, payload.model_dump())


@router.get("/feedback/{request_id}")
@router.get("/requests/{request_id}")
async def feedback_status(
    request_id: str, service: PipelineQualityService = Depends(quality)
):
    return await call(service.feedback_verdict, request_id)


@router.post("/feedback/{request_id}/evaluate")
@router.post("/requests/{request_id}/evaluate")
async def evaluate_feedback(
    request_id: str, service: PipelineQualityService = Depends(quality)
):
    return await call(service.feedback_verdict, request_id, evaluate=True)
