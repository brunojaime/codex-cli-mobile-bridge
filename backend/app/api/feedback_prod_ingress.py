"""Official Feedback contract ingress for an existing PROD Bridge.

Uses the shared validated schema and durable admission ledger. No capture/queue
engine is copied into a consumer; the legacy PROD executor is never restarted.
"""
from __future__ import annotations
import json
import os
from pathlib import Path

import httpx
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool

from backend.app.api.schemas import FeedbackBatchStartRequest
from backend.app.application.services.feedback_submission import FeedbackSubmissions, SubmissionConflict


def create_app(*, backend_url: str, ledger_path: Path, consumers: dict, handoff_file: Path | None = None, transport=None):
    if backend_url != 'http://127.0.0.1:8000':
        raise ValueError('EXACT_PROD_BRIDGE_TARGET_REQUIRED')
    app = FastAPI(title='Codex Bridge official PROD Feedback ingress')
    app.add_middleware(CORSMiddleware, allow_origins=[c['origin'] for c in consumers.values()], allow_methods=['GET', 'POST'], allow_headers=['content-type'])
    router = APIRouter()
    ledger = FeedbackSubmissions(ledger_path)

    async def backend(path, *, payload=None):
        async with httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(600, connect=15)) as client:
            return await (client.get(backend_url + path) if payload is None else client.post(backend_url + path, json=payload))

    async def prod_health():
        response = await backend('/health')
        if response.status_code != 200 or response.json().get('environment_identity', {}).get('environment') != 'prod':
            raise HTTPException(503, 'Verified PROD executor required; no alternate destination')
        return {'environment': 'prod', 'verified': True}

    @router.get('/health')
    async def health():
        return await prod_health()

    @router.get('/feedback-contract')
    async def contract():
        return {'kind': 'codex.feedbackContract', 'version': 1, 'supportedBatchVersions': [1, 3], 'canonicalBatchVersion': 3, 'submissionPath': '/feedback-batches/start-session', 'idempotentSubmissions': True, 'submissionStatusPath': '/feedback-submissions/{batchId}', 'releaseRequestExpandsAuthority': False, 'executorEnvironment': 'prod'}

    @router.get('/feedback-workflow-presets')
    async def presets():
        response = await backend('/feedback-workflow-presets')
        if response.status_code != 200:
            raise HTTPException(503, 'PROD presets unavailable')
        return response.json()

    @router.get('/feedback-submissions/{batch_id}')
    async def status(batch_id: str):
        result = await run_in_threadpool(ledger.status, batch_id)
        if result is None:
            raise HTTPException(404, 'Feedback submission not found')
        return result

    @router.post('/feedback-batches/start-session', status_code=202)
    async def start(payload: FeedbackBatchStartRequest, request: Request):
        consumer = consumers.get(payload.sourceApp)
        if (consumer is None or not payload.items or payload.session_id is not None
            or payload.release_when_complete or payload.workspace_path not in (payload.sourceApp, consumer['workspace'])
            or any(item.contextMetadata.get('environment') != 'dev' for item in payload.items)):
            raise HTTPException(403, 'Authorized development consumer and exact workspace required')
        if request.headers.get('origin') not in (None, consumer['origin']):
            raise HTTPException(403, 'Exact consumer origin required')
        await prod_health()
        canonical = payload.model_dump(mode='json', exclude_none=True)
        try:
            reservation = await run_in_threadpool(ledger.reserve, canonical)
        except SubmissionConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        if reservation['state'] == 'accepted':
            return reservation['receipt']
        if reservation['state'] != 'new':
            raise HTTPException(409, {'code': 'feedback_submission_in_progress_or_uncertain', 'batchId': reservation['id'], 'statusPath': '/feedback-submissions/' + reservation['id']})
        try:
            dispatched = dict(canonical)
            # Trusted migration context changes execution instructions, not the
            # original content-addressed submission or the browser's queue.
            if handoff_file and handoff_file.is_file():
                handoffs = json.loads(handoff_file.read_text())
                if reservation['id'] in handoffs:
                    dispatched['message'] = handoffs[reservation['id']]
            response = await backend('/feedback-batches/start-session', payload=dispatched)
            if response.status_code != 202:
                raise HTTPException(502, {'code': 'prod_feedback_not_accepted', 'upstreamStatus': response.status_code, 'batchId': reservation['id']})
            receipt = response.json()
            if not receipt.get('job_id') or not receipt.get('session_id'):
                raise HTTPException(502, 'PROD receipt missing job/session; reconcile before retry')
            await run_in_threadpool(ledger.finish, reservation['id'], reservation['owner'], receipt)
            return receipt
        except BaseException:
            await run_in_threadpool(ledger.finish, reservation['id'], reservation['owner'], None)
            raise

    app.include_router(router)
    # Tailscale Serve revisions differ in prefix stripping. Both paths invoke
    # exactly the same router and admission ledger, never a second receiver.
    app.include_router(router, prefix='/bridge-feedback-prod')
    return app


def configured_app():
    config = json.loads(Path(os.environ['CODEX_FEEDBACK_INGRESS_CONFIG']).read_text())
    return create_app(backend_url=config['backend_url'], ledger_path=Path(config['ledger_path']), consumers=config['consumers'], handoff_file=Path(config['handoff_file']) if config.get('handoff_file') else None)
