# Reviewed recovery of an uncertain DEV Feedback batch — 2026-11-05

User scope: fix Cebando Tradición DEV reception and retain the phone's pending feedback. No production changes, queue deletion, automatic submissions or new agents as tests.

The quality validator retains its stage root and adds only the exact Cebando workspace through private runtime configuration. Public SDK/artifacts and consumer cookies/queue scopes remain unchanged. All existing legacy feedback data and sessions remain in their current persistence paths.

`FeedbackSubmissions.authorize_reviewed_retry` is a trusted local operator operation, not an HTTP reset. It requires an uncertain row with no receipt, reviewed empty preliminary session, no runs/messages and drained DEV. The operator reads canonical health, drain, session and submission status before applying. A durable append-only review stores the prior state and unchanged digest; state becomes retryable. Reserve admits the same content/ID once, issues a fresh owner and retains hash-conflict rejection and receipt replay. Stale owners cannot finish it. Accepted or in-flight submissions cannot be released by this operation. No deletion or content reconstruction.

Acceptance: concurrency/restart/receipt/conflict/evidence tests; live exact-project quality GET passes; unrelated workspace remains denied; canonical batch status retryable after reviewed recovery; zero requests submitted by operator. The pending phone content stays local until the user explicitly sends again. A live successful receipt is recorded separately when it arrives.
