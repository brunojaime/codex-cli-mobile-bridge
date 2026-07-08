# Validation And Tests

Add focused tests for contract parsing, path safety, dry-run creation, existing
spec edit targeting, metadata refresh, pinned fields, task summaries, context
pack use, Codex CLI job state output, and no broad spec fallback.

This phase consolidates doctor/readiness checks and end-to-end fixtures. It must
run strict doctor against generated fixture workspaces and prove no unintended
writes outside the destination repo.
