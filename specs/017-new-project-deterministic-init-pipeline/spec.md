# New Project Deterministic Init Pipeline

id: 017-new-project-deterministic-init-pipeline
status: planned
owner: codex-mobile-bridge

## Intent

Change the New Project button so it starts with a deterministic initialization
pipeline before any business/product LLM work begins.

The pipeline should create a real baseline project, publish the baseline
infrastructure where configured, and open the first project chat with a complete
context pack. The LLM should receive an already-created app, repository,
preview/runtime contract, Workbench wiring, feedback wiring, and release state.
The LLM then focuses on the business domain instead of recreating repeated
project bureaucracy.

This spec complements:

- `005-new-project-factory`
- `006-web-preview-delivery`
- `007-initial-preview-release`
- `011-new-project-guided-intake`
- `014-project-factory-frontend-strategy`
- `015-project-factory-preview-hardening`
- `013-workbench-kanban-curator`

## Product Outcome

When the user taps New Project:

- the app opens or creates a New Project chat immediately;
- the backend creates or resumes a Project Factory draft;
- a deterministic init job starts before any business implementation prompt;
- the init job creates the project baseline under `PROJECTS_ROOT`;
- the init job creates or verifies the GitHub repository when remote publication
  is configured;
- the init job pushes the baseline commit;
- the init job prepares the Cloudflare preview URL and Preview API URL;
- the init job creates or verifies Cloudflare Worker, route, D1 database,
  baseline migrations, and preview smoke checks when credentials are available;
- the init job wires the selected frontend strategy, defaulting to Flutter for
  installable mobile projects;
- the init job wires Workbench, SDD, feedback bridge, updater, runtime profiles,
  release scripts, and validation scripts;
- the init job creates the Initial Preview Release artifacts when remote
  publication is configured and supported;
- the init job registers the installable app in Bridge when the selected
  strategy supports it;
- the first chat receives a persisted context pack with project path, repo URL,
  preview URL, API URL, runtime profile, release state, Workbench/feedback
  state, generated files, blockers, and next safe LLM instructions;
- after init finishes, the user can start the project conversation in that same
  chat with the full baseline already available.

The user should experience New Project as "create the real project foundation
first, then discuss the product", not as "ask the LLM to remember all setup
steps".

## Core Rules

- Deterministic init must run before the first business/product LLM pass.
- The deterministic init pipeline must not depend on LLM output.
- New Project button behavior changes from guided-only creation to
  chat-plus-init creation.
- The first chat must be opened or selected immediately and linked to the draft
  and init job.
- The init pipeline must be idempotent and resumable by phase.
- Every phase must write structured status, command evidence, stdout/stderr
  summaries, produced artifacts, and blockers.
- Init may create real remote resources only after preflight confirms the
  required credentials and target configuration.
- Missing credentials must block the relevant remote phase with exact next
  actions, not silently skip or claim readiness.
- Secrets must never be written to generated repositories, chat context packs,
  logs, or release artifacts.
- Initial preview uses real preview infrastructure by default:
  `APP_RUNTIME_PROFILE=preview`, `API_RUNTIME=cloudflare_preview`, and
  `https://preview.nienfos.com/{slug}/api`.
- Mock/demo mode remains opt-in and must be visible in versioning, tags, and
  final reports if explicitly requested.
- Production release remains out of scope for New Project init.
- Remote publication creates preview/prerelease artifacts, not production
  claims.
- A baseline release before business implementation must be labeled as an
  Initial Preview Baseline.
- The LLM context pack must be generated from structured init state, not from
  loose natural-language summaries.
- The LLM must receive the context pack as the default starting context for the
  first project chat.
- Existing Project Factory generation, guided intake, Workbench, release, and
  installable-app systems must remain compatible.

## Deterministic Init Phases

The first delivery should implement these phases as a single resumable init
pipeline. Phase names are stable because UI, history, and tests will reference
them.

1. `init_preflight`
   - Verify local toolchain: git, gh, wrangler, flutter, dart, Python, Codex CLI.
   - Verify Bridge configuration and `PROJECTS_ROOT`.
   - Verify GitHub authentication when repository creation is requested.
   - Verify Cloudflare credentials when preview publication is requested.
   - Verify Android signing and release config when Android preview is requested.

2. `draft_and_slug`
   - Create or reuse a guided Project Factory draft.
   - Resolve project name, slug, frontend strategy, first release mode, and
     baseline target path.
   - Calculate preview URL and API URL.
   - Detect conflicts before writing local or remote state.

3. `baseline_scaffold`
   - Generate the local project foundation deterministically.
   - Include `.codex/project.yaml`, `codex-bridge.yaml`, `AGENTS.md`, README,
     SDD artifacts, Workbench metadata, release contracts, validation scripts,
     Cloudflare preview files, backend scaffold, and selected frontend scaffold.

4. `flutter_or_strategy_baseline`
   - Install or verify selected frontend strategy dependencies.
   - For Flutter, create mobile/web baseline, Android project, runtime profile
     wiring, app updater, feedback bridge integration, and Workbench hooks.
   - For non-Flutter strategies, enforce strategy capability limits.

5. `local_validation`
   - Run deterministic baseline validation before remote publication.
   - Verify no localhost, mock, placeholder, or example API URLs are used for
     preview release configuration.

6. `local_git_commit`
   - Initialize git if needed.
   - Commit the baseline foundation with a generated commit message.
   - Refuse to report completion when files remain unintentionally untracked.

7. `github_repository`
   - Create or verify the GitHub repository.
   - Add or verify `origin`.
   - Push the baseline branch.
   - Persist repo URL, default branch, and push status.

8. `cloudflare_preview_provision`
   - Create or verify the preview Worker, route, D1 database, and required
     Cloudflare settings for `https://preview.nienfos.com/{slug}`.
   - Apply baseline D1 migrations.
   - Bind Worker, D1, static assets, and required non-secret environment values.

9. `cloudflare_preview_deploy`
   - Deploy the baseline preview.
   - Verify Worker update behavior.
   - Verify app shell, protected routes, `/api/health`, invite/access routes,
     static asset MIME types, and cache headers.

10. `preview_smoke`
    - Run web preview smoke tests.
    - Run Preview API smoke tests.
    - Persist public URLs and smoke evidence.

11. `android_preview_release`
    - For Flutter/installable strategies, build the Android preview APK against
      the real preview API.
    - Create a GitHub prerelease using `android-preview-v*`.
    - Verify APK asset, release metadata, updater metadata, and no mock/demo
      flags.

12. `bridge_installable_registration`
    - Register or update the Bridge installable app entry.
    - Verify installable app discovery points to the preview release artifact.

13. `workbench_and_feedback_verification`
    - Verify Workbench can discover the generated project.
    - Verify SDD metadata and context routing.
    - Verify Codex developer feedback routing, source app identity, updater URL,
      and queue behavior.

14. `llm_context_pack`
    - Write `.codex/factory/init-result.json`.
    - Write `.codex/factory/llm-start-context.md`.
    - Attach the context pack to the first chat/session.
    - Mark business LLM work as ready only after init reaches `ready` or a
      user-visible `blocked_with_context` state.

## LLM Context Pack Contract

The context pack must include:

- draft id and init job id;
- project name, slug, path, and frontend strategy;
- GitHub repository URL and branch;
- preview URL and API base URL;
- runtime profile and API runtime;
- D1 database identity or blocked reason;
- Cloudflare Worker and route identity or blocked reason;
- Android preview release URL or blocked reason;
- Bridge installable app id/status or blocked reason;
- Workbench discovery status;
- feedback bridge status;
- generated files summary;
- validation commands that passed;
- remote commands that ran;
- unresolved blockers with exact next actions;
- rules for the LLM business phase:
  - keep preview runtime real;
  - do not switch to mock/demo unless the user explicitly requests it;
  - do not recreate GitHub, Cloudflare, D1, release, feedback, or Workbench
    plumbing manually;
  - implement only product/business work on top of the initialized baseline;
  - update specs, tasks, tests, and release evidence as product work changes.

## New Project UI Contract

The New Project button must:

- create or focus the first New Project chat;
- start or resume the deterministic init job;
- show init progress in the chat timeline;
- show phase statuses with concrete blockers and commands;
- disable business build actions until init is ready or explicitly continued
  with blocked context;
- keep the chat open after init completes;
- show a clear "Start product conversation" affordance once the LLM context pack
  is attached;
- preserve the chat, draft, init job, generated workspace, and Workbench scope
  relationship across app restarts.

The user should not need to open a separate Project Factory screen to recover
the job. New Project chat is the primary surface.

## Backend Contract

Add a deterministic init service and runner that separate setup from business
LLM work.

Recommended service boundaries:

- `ProjectFactoryInitService`: creates/resumes init state, exposes API payloads,
  and owns persistence.
- `ProjectFactoryInitRunner`: executes deterministic phases.
- `ProjectFactoryInitPreflight`: reports credential/tool readiness.
- `ProjectFactoryRemoteProvisioner`: wraps GitHub and Cloudflare operations.
- `ProjectFactoryInitContextPackService`: writes and attaches the LLM context
  pack.

Existing `ProjectFactoryJobRunner` can continue to own generator/reviewer
business work, but it should receive the init result instead of recreating
baseline bureaucracy.

## API Contract

Expose or extend endpoints for:

- start/resume New Project init from the button;
- get init job status;
- stream init progress;
- get init result/context pack;
- retry failed phase;
- continue to business chat when init is ready;
- list draft/job/chat/workspace relationships.

The API must preserve existing guided intake endpoints and avoid breaking older
drafts.

## Persistence Contract

Persist init state outside generated repositories and outside SDD artifacts.

State must include:

- draft id;
- chat/session id;
- init job id;
- phase statuses;
- command evidence;
- local project path;
- remote resource identifiers;
- generated artifact summary;
- context pack path and hash;
- blockers and retry hints;
- timestamps;
- workspace mapping after the project exists.

Generated projects may contain a copy of `init-result.json`, but Bridge remains
the authority for job state and recovery.

## Non-Goals

- Do not implement production promotion in this spec.
- Do not make mock/demo the default.
- Do not remove guided intake; integrate it with deterministic init.
- Do not rely on the LLM to create GitHub, Cloudflare, D1, release, Workbench,
  or feedback setup.
- Do not expose secrets in generated repos or chat messages.
- Do not require every frontend strategy to produce an Android artifact.
- Do not change existing released APK policy for Codex Mobile Bridge itself.

## Acceptance Criteria

- Pressing New Project creates or focuses a first chat and starts/resumes
  deterministic init.
- Init can complete without running business/product LLM prompts.
- Init creates a local baseline project with deterministic artifacts.
- Init creates and pushes a GitHub repository when configured credentials are
  available.
- Init prepares Cloudflare preview URL, Preview API URL, Worker, D1, baseline
  migrations, and smoke tests when configured credentials are available.
- Init creates an Android preview prerelease and Bridge installable app entry
  for Flutter/installable strategies when configured credentials are available.
- Init verifies Workbench, SDD, feedback bridge, updater, runtime profile, and
  release contracts.
- Missing external credentials produce blocked phases with exact commands and
  do not prevent local baseline and context pack creation.
- The first chat receives a persisted LLM context pack after init.
- The LLM business phase starts with the initialized project context and does
  not repeat deterministic setup work.
- Tests cover service state, phase idempotency, API payloads, UI behavior,
  context pack contents, Cloudflare/GitHub command construction, release
  guardrails, and blocked recovery.
