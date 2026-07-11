# Deterministic GitHub Repository Creation And Baseline Push

Move GitHub setup into the init pipeline so the LLM receives a real repository
instead of instructions to create one.

Status: completed

## Deterministic Pipeline Scope

- GitHub auth and permission preflight.
- Repository create-or-verify behavior.
- Origin setup.
- Baseline branch push.
- Persisted repository URL, branch, command evidence, and recovery blockers.

## Tasks

- [x] T011 Add GitHub preflight for `gh` auth, owner/repo availability, permissions, branch policy, and push capability.
- [x] T012 Implement deterministic GitHub repo create-or-verify behavior with no duplicate repos.
- [x] T013 Implement origin setup and baseline branch push as an init phase.
- [x] T014 Persist GitHub repo URL, branch, remote status, and command evidence.
- [x] T015 Add blocked GitHub recovery payloads with exact commands and missing configuration.
