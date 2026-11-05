#!/usr/bin/env python3
"""Local DEV operator: review an uncertain batch; never submit it or delete data."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.application.services.feedback_submission import FeedbackSubmissions


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch-id', required=True)
    parser.add_argument('--session-id', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    base = 'http://127.0.0.1:8118'
    def get(path):
        with urlopen(base + path, timeout=15) as r:
            return json.load(r)
    health = get('/health')
    if health.get('environment_identity', {}).get('environment') != 'dev':
        raise RuntimeError('DEV_REQUIRED')
    drain = get('/maintenance/drain')
    if not drain.get('requested') or not drain.get('ready_to_restart'):
        raise RuntimeError('DRAIN_WITH_ZERO_ACTIVE_OPERATIONS_REQUIRED')
    session = get('/sessions/' + args.session_id)
    if session.get('workspace_path') != '/home/batata/Projects/cebandotradicion':
        raise RuntimeError('EXACT_CONSUMER_SESSION_REQUIRED')
    if session.get('messages') or session.get('current_run') or session.get('recent_runs'):
        raise RuntimeError('SESSION_HAS_SIDE_EFFECTS_DO_NOT_RETRY')
    status = get('/feedback-submissions/' + args.batch_id)
    if status.get('state') != 'uncertain' or status.get('receipt') is not None:
        raise RuntimeError('UNCERTAIN_WITHOUT_RECEIPT_REQUIRED')
    ledger_path = Path('/home/batata/Projects/codex-cli-mobile-bridge/.run/dev-backend-8118/data/feedback_queue.submissions.sqlite3')
    if not ledger_path.is_file():
        raise RuntimeError('EXISTING_DEV_LEDGER_REQUIRED')
    evidence = {
        'environment': 'dev', 'sourceApp': 'cebandotradicion',
        'session_id': args.session_id, 'session_messages': 0, 'session_runs': 0,
        'no_active_operations': True, 'verified_at': datetime.now(timezone.utc).isoformat(),
        'reason': 'Human-requested recovery after exact workspace-scope denial before any job; canonical session has no messages or runs, no receipt; DEV drained. Preserve batch ID/digest and original session. No resubmission by operator.',
    }
    if args.apply:
        result = FeedbackSubmissions(ledger_path).authorize_reviewed_retry(args.batch_id, evidence)
    else:
        result = {'id': args.batch_id, 'state': 'review-only', 'evidence': evidence}
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
