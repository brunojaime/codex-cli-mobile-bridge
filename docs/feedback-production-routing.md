# Common Feedback receiver: production executor

Authorized request 2026-11-09, session 4b65f42e-c434-42e1-a82a-dc0a7da3292b:
publish the SEA changes to SEA DEV, and run all application Feedback in Bridge PROD.
Consumer DEV visibility remains separate from the Bridge execution environment.

The official PROD ingress verifies the upstream environment before admission,
resolves configured workspace aliases on the server and accepts exact configured
browser origins. Native clients omit Origin. It never falls back to DEV.

Read-only historical ledgers preserve receipts across receiver migration. A
matching accepted batch returns its original receipt without another dispatch;
conflicting content, divergent histories and uncertain/inflight requests remain
blocked for reviewed reconciliation. Historical records are never overwritten.
The current ledger retains ownership, content digest and idempotent receipts.

The HTTPS proxies change only Feedback paths. Other DEV API paths and other
Tailscale handlers remain unchanged. Existing sourceApp, queue keys, batch IDs,
captures and audio stay intact. A receiver switch does not authorize application
QA/production publication or real-agent smoke tests.

Validation: tests/test_feedback_prod_ingress.py and test_feedback_submission.py;
25 tests including original DEV receipts, uncertainty, concurrent retries,
workspace/origin denial, PROD health verification and backlog receipt negotiation.
The PROD executor itself is not restarted; only its ingress sidecar changes.
