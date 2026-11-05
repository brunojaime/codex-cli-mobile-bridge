# Reviewed recovery of an uncertain DEV Feedback batch — 2026-11-05

User scope: fix Cebando Tradición DEV reception and retain the phone's pending feedback. No production changes, queue deletion, automatic submissions or new agents as tests.

The quality validator retains its stage root and adds only the exact Cebando workspace through private runtime configuration. Public SDK/artifacts and consumer cookies/queue scopes remain unchanged. All existing legacy feedback data and sessions remain in their current persistence paths.

`FeedbackSubmissions.authorize_reviewed_retry` is a trusted local operator operation, not an HTTP reset. It requires an uncertain row with no receipt, reviewed empty preliminary session, no runs/messages and drained DEV. The operator reads canonical health, drain, session and submission status before applying. A durable append-only review stores the prior state and unchanged digest; state becomes retryable. Reserve admits the same content/ID once, issues a fresh owner and retains hash-conflict rejection and receipt replay. Stale owners cannot finish it. Accepted or in-flight submissions cannot be released by this operation. No deletion or content reconstruction.

Acceptance: concurrency/restart/receipt/conflict/evidence tests; live exact-project quality GET passes; unrelated workspace remains denied; canonical batch status retryable after reviewed recovery; zero requests submitted by operator. The pending phone content stays local until the user explicitly sends again. A live successful receipt is recorded separately when it arrives.


## Explicit destination correction to the PROD engine — 2026-11-05

Owner explicitly requests cancelling the Cebando DEV job and transferring the original batch to Bridge PROD, including future submissions; the app itself remains DEV. PROD has the legacy receiver and active jobs, so a separately managed private ingress composes the approved Feedback schema and durable ledger with that existing executor. It does not restart or modify the PROD executor, nor replace routes of other consumers. Exact consumer/origin/workspace, development screenshots, supported protocol and releaseWhenComplete=false are enforced server-side. No fallback to DEV. Only the exact private path is added to Tailscale Serve. The consumer uses the SDK's public bridgeUrl option; no local transport engine or fetch injection.

Migration reconstructs the accepted original batch and verifies its normalized SHA-256 against the DEV ledger before sending. Same batch ID, image/audio bytes and browser queue scope persist. A trusted private continuation note contains the original transcriptions and instructs preserving partial DEV edits. The normalized browser content identity remains immutable; retries get the same PROD receipt. Tests use an ASGI fake executor; the only real submission is the owner-authorized migration.
