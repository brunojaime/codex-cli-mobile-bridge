# Workbench Kanban Curator

id: 013-workbench-kanban-curator
status: complete
owner: codex-mobile-bridge

## Intent

Add a Workbench Kanban view that shows spec progress as cards moving through deterministic columns, plus a read-only Curator that periodically explains what changed in friendly language.

The Kanban must work for normal repository specs and for New Project work where the target repository may not exist yet. Generator and Reviewer should continue to behave as they do today in chat. This feature observes their work and the existing SDD artifacts; it must not add obligations to Generator or Reviewer.

## Product Outcome

When a spec is being worked on, the user can open the Workbench and see:

- a Kanban board for the active spec;
- cards derived from the existing spec, plan, task, run, review, test, and release state;
- the latest Curator update explaining what just happened;
- a history view of prior Curator updates with timestamps and evidence;
- continuity from New Project draft/job scope into the generated repository workspace once that repository exists.

Generator and Reviewer messages stay in the normal chat transcript. The Curator is visible in Workbench surfaces, not as another actor interrupting the chat.

## Core Rules

- Do not modify Generator or Reviewer behavior for the first delivery.
- Do not require Generator or Reviewer to emit new events.
- Do not store Kanban state inside `spec.md`, `plan.md`, `tasks.md`, `tree.json`, or spec metadata.
- Derive confirmed task movement from existing SDD task state and existing run/review artifacts.
- Keep inferred activity visually distinct from confirmed task completion.
- Make the board deterministic: the same input snapshot must produce the same cards, columns, ordering, and counts.
- Curator updates are read-only summaries of observed state; they cannot change task status, approve work, reject work, or trigger Generator/Reviewer.
- The Curator may run on a debounce after meaningful observed changes and on a low-frequency timer while work is active.
- The Kanban must work before a New Project target repository exists by scoping to draft/job identity.
- When a generated repository appears, the board must preserve history and re-scope to the workspace without duplicating cards.
- History must be append-only and stored outside SDD artifacts.
- The latest Curator update must be visible without opening history.

## Kanban Columns

The first delivery should use a small fixed set of columns:

- `Backlog`: planned spec tasks not ready or not yet touched.
- `Ready`: planned tasks available for work based on phase ordering and dependencies.
- `In Progress`: tasks or run steps with evidence of active work but no confirmed completion.
- `Review`: completed work waiting on Reviewer, unresolved findings, or validation.
- `Blocked`: tasks blocked by explicit error, missing input, failed validation, or external release requirement.
- `Done`: tasks confirmed complete by SDD task state or accepted validation evidence.

Column membership must be computed from deterministic rules. User-facing labels can be localized later, but internal states should remain stable.

## Card Types

The board should support these card types:

- `spec_task`: one card per SDD task from `tasks.md` and `tree.json`.
- `plan_phase`: optional summary cards for phase-level progress.
- `run_step`: inferred cards for active Generator, Reviewer, command, test, build, or release steps.
- `review_finding`: cards for unresolved Reviewer findings when they can be parsed from existing artifacts.
- `blocker`: cards for explicit errors, missing approvals, failed checks, or release gates.

Confirmed `spec_task` card movement is authoritative only when existing SDD task status changes. `run_step`, `review_finding`, and `blocker` cards can be inferred from job state, transcripts, logs, or test records, but they must display as observed/inferred evidence rather than confirmed task completion.

## Curator Behavior

The Curator is a passive observer. It receives a compact board snapshot, recent evidence, previous Curator update, and recent deltas. It writes a human-friendly update with:

- timestamp;
- scope and spec id;
- current phase/run context when known;
- short summary;
- changed cards/tasks;
- important evidence;
- blockers or risks;
- next likely thing to watch.

The Curator should not do code review. Reviewer remains responsible for review. The Curator can mention that Reviewer appears to be reviewing, that findings appeared, or that findings were resolved, but it must not replace Reviewer judgement.

## Triggering Model

The deterministic projection should update whenever watched sources change:

- SDD artifacts: `metadata.yaml`, `tasks.md`, `tree.json`, `plan.md`;
- persisted Project Factory job/draft state;
- known run/session state;
- Codex JSONL or transcript window sources when available;
- command/test/build status files or records;
- generated repository existence and workspace mapping.

The Curator should run after a debounced meaningful board delta and on a periodic timer while a spec or job is active. It should skip writing a new update when the evidence hash is unchanged or the only changes are noise.

Recommended initial policy:

- projection refresh: event-driven when possible, with polling fallback;
- Curator debounce: short delay after meaningful deltas;
- Curator interval: low-frequency while active;
- Curator history: append-only, capped by retention settings in the Workbench data store.

## Workbench Placement

Add a primary Workbench tab named `Kanban`, placed with the existing spec-oriented views. The Kanban view owns the full board, latest Curator update, and history access.

Also add a compact latest-update card to the Workbench overview so the user can see the newest Curator summary without switching tabs.

The chat transcript should continue to show Generator, Reviewer, assistant, and user messages normally. The Curator should not flood chat.

## History Experience

The Kanban view shows only the latest Curator update by default. A `View history` affordance opens a reverse-chronological list of previous updates.

Each history row should show:

- friendly timestamp;
- phase/run label when known;
- short title or summary;
- changed counts;
- blocker indicator when present.

Opening a history item shows the full Curator update, evidence references, changed cards, and relevant links back to tasks, runs, or files.

## New Project Continuity

Before the target repository exists, the board scopes to the New Project draft/job. It can show generated planning tasks, active generator/reviewer run steps, readiness gates, and blockers from persisted Project Factory state.

After the target repository exists, the board links the draft/job scope to the new workspace scope. Curator history should remain visible as one timeline, with a clear marker that the scope moved from draft/job to repository workspace.

## Non-Goals

- Do not redesign the SDD spec format.
- Do not change the spec/plan/task tree to store Kanban state.
- Do not modify Generator or Reviewer prompts in this spec.
- Do not add a new Reviewer replacement.
- Do not publish an Android release unless explicitly requested.
- Do not touch generated project repositories as part of this spec.

## Acceptance Criteria

- A Workbench Kanban tab renders cards for an active spec from existing SDD artifacts.
- Confirmed task cards move deterministically from existing task state.
- Inferred run/review/test/build cards are visibly distinct from confirmed task cards.
- Curator produces a latest update and append-only history outside SDD artifacts.
- Curator does not modify Generator, Reviewer, task status, or spec files.
- Generator and Reviewer continue to appear in chat as before.
- New Project jobs show board state before repository creation and preserve history after workspace creation.
- The same source snapshot produces the same board snapshot.
- Tests cover projection, task-state mapping, history persistence, Curator dedupe, API payloads, and mobile UI states.
