# Central feedback backlog DEV delivery

Merge release/backlog-night-157 with the approved feedback v3 distribution. Preserve durable storage, legacy queues, alias routing, content SHA-256, audio and conformance. Native UI uses the official client. Delayed preset loading completes before hashing a submitted batch.

Build with scripts/build_feedback_release.py --output DEST --id feedback-20261105-dev.4 after tests. Each artifact and all distributed sources are hashed. Install only with scripts/adopt_feedback_release.py, run the packaged verifier, then validate the actual DEV entrypoint and deployment receipt. Do not distribute APKs or restart production.

Backend acceptance: controlled feedback receipt test verifies backlogId, durable screenshot, duplicate replay, conflict and zero sessions. Clients preserve payload identities on retry/recreation. Consumer drift remains separate from published runtime evidence in Gestión.
