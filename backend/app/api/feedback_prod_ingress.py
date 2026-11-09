"""Official Feedback contract ingress for an existing PROD Bridge.

Uses the shared validated schema and durable admission ledger. No capture/queue
engine is copied into a consumer; the legacy PROD executor is never restarted.
"""
from __future__ import annotations
import json
import os
import sqlite3
from pathlib import Path

import httpx
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool

from backend.app.api.schemas import FeedbackBatchStartRequest
from backend.app.application.services.feedback_submission import FeedbackSubmissions, SubmissionConflict


def create_app(*, backend_url: str, ledger_path: Path, consumers: dict, handoff_file: Path | None = None, legacy_ledgers: tuple[Path, ...] = (), transport=None):
    if backend_url != 'http://127.0.0.1:8000':
        raise ValueError('EXACT_PROD_BRIDGE_TARGET_REQUIRED')
    app = FastAPI(title='Codex Bridge official PROD Feedback ingress')
    app.add_middleware(CORSMiddleware, allow_origins=sorted({o for c in consumers.values() for o in c.get('origins', [c.get('origin')]) if o}), allow_methods=['GET', 'POST'], allow_headers=['content-type'])
    router = APIRouter()
    ledger = FeedbackSubmissions(ledger_path)

    def legacy_status(identity: str, canonical: dict | None = None, *, paths=None):
        records = []
        for path in (legacy_ledgers if paths is None else paths):
            if not path.is_file():
                continue
            with sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True) as db:
                row = db.execute('SELECT digest,state,receipt FROM submissions WHERE id=?', (identity,)).fetchone()
            if row is None or row[1] == 'retryable':
                continue
            if canonical is not None and row[0] != FeedbackSubmissions.identity(canonical)[1]:
                raise HTTPException(409, 'legacy_batch_id_content_conflict')
            records.append({'id': identity, 'state': row[1], 'receipt': json.loads(row[2]) if row[2] else None})
        if not records:
            return None
        # Divergent histories require review, never an arbitrary receipt or a new job.
        if any(record != records[0] for record in records[1:]):
            raise HTTPException(409, 'legacy_feedback_histories_require_review')
        return records[0]

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
        value = {'kind': 'codex.feedbackContract', 'version': 1, 'supportedBatchVersions': [1, 3], 'canonicalBatchVersion': 3, 'submissionPath': '/feedback-batches/start-session', 'idempotentSubmissions': True, 'submissionStatusPath': '/feedback-submissions/{batchId}', 'releaseRequestExpandsAuthority': False, 'executorEnvironment': 'prod', 'supportedExecutionModes': ['execute']}
        upstream = await backend('/feedback-contract')
        if upstream.status_code == 200:
            capabilities = upstream.json()
            if ('backlog' in capabilities.get('supportedExecutionModes', [])
                and 3 in capabilities.get('supportedBatchVersions', [])
                and capabilities.get('idempotentSubmissions') is True
                and capabilities.get('backlogReceiptField') == 'backlogId'):
                value.update(supportedExecutionModes=['execute', 'backlog'], backlogReceiptField='backlogId')
        return value

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
            result = await run_in_threadpool(legacy_status, batch_id)
        if result is None:
            raise HTTPException(404, 'Feedback submission not found')
        return result

    @router.post('/feedback-batches/start-session', status_code=202)
    async def start(payload: FeedbackBatchStartRequest, request: Request):
        consumer = consumers.get(payload.sourceApp)
        if (consumer is None or not payload.items or payload.session_id is not None
            or payload.release_when_complete or payload.workspace_path not in (None, payload.sourceApp, consumer['workspace'], *consumer.get('aliases', []))
            or any(item.contextMetadata.get('environment') != 'dev' for item in payload.items)):
            raise HTTPException(403, 'Authorized development consumer and exact workspace required')
        if request.headers.get('origin') not in (None, *consumer.get('origins', [consumer.get('origin')])):
            raise HTTPException(403, 'Exact consumer origin required')
        await prod_health()
        if payload.execution_mode == 'backlog':
            capabilities = await contract()
            if 'backlog' not in capabilities['supportedExecutionModes']:
                raise HTTPException(409, 'PROD backlog capability not advertised; queue retained')
        canonical = payload.model_dump(mode='json', exclude_none=True)
        identity, _ = FeedbackSubmissions.identity(canonical)
        # This ingress already owns the definitive receipt after its own admission.
        # A late-discovered legacy record cannot replace it or invalidate a retry.
        owned = await run_in_threadpool(legacy_status, identity, canonical, paths=(ledger.path,))
        if owned is not None:
            if owned['state'] == 'accepted' and owned['receipt']:
                return owned['receipt']
            raise HTTPException(409, {'code': 'feedback_submission_in_progress_or_uncertain', 'batchId': identity, 'statusPath': '/feedback-submissions/' + identity})
        previous = await run_in_threadpool(legacy_status, identity, canonical)
        if previous is not None:
            if previous['state'] == 'accepted' and previous['receipt']:
                return previous['receipt']
            raise HTTPException(409, {'code': 'legacy_feedback_requires_reconciliation', 'batchId': identity, 'statusPath': '/feedback-submissions/' + identity})
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
            # Resolve the server-owned alias without changing original admission identity.
            if consumer.get('resolveWorkspace'):
                dispatched['workspace_path'] = consumer['workspace']
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
            valid_receipt = (isinstance(receipt.get('backlogId'), str) and bool(receipt['backlogId'].strip())) if payload.execution_mode == 'backlog' else bool(receipt.get('job_id') and receipt.get('session_id'))
            if not valid_receipt:
                raise HTTPException(502, 'PROD receipt missing required identity; reconcile before retry')
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
    return create_app(backend_url=config['backend_url'], ledger_path=Path(config['ledger_path']), consumers=config['consumers'], legacy_ledgers=tuple(Path(p) for p in config.get('legacy_ledgers', [])), handoff_file=Path(config['handoff_file']) if config.get('handoff_file') else None)
