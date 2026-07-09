---
id: 005-new-project-factory
title: New Project Factory
status: accepted
type: feature
domains:
  - project-factory
  - workbench
  - flutter
  - sdd
  - release-readiness
---

# New Project Factory

## Intent

Codex Mobile Bridge must expose a user-facing "New project" flow that creates a
new sibling project under `PROJECTS_ROOT` and leaves it ready for Codex-driven
development through Workbench specs, plans, and tasks.

The generated project is not a bare scaffold. It must include a Flutter
iOS/Android/Web app, a backend template, authentication, Google sign-in
configuration placeholders, extensible roles and permissions, an admin area,
domain-management foundations, notifications, Codex Feedback Bridge, app
updater wiring, Workbench/SDD artifacts, research outputs, visual direction, and
release-readiness documentation.

## Scope

- A chat-mode "New project" entry in the existing mobile/workbench app.
- A backend project-factory API with draft, dry-run, generate, history,
  reference-asset, doctor, and job status flows.
- A validated `.codex/project.yaml` manifest contract.
- Local project creation under `PROJECTS_ROOT`.
- Local git initialization and an initial committed baseline are mandatory.
- GitHub publication is part of the publish contract: create/verify the remote,
  push the branch, and record any missing credentials as an explicit blocked
  publish state rather than silently completing.
- Android release publication and Codex Mobile installable-app registration are
  part of the same publish contract. A generated project is not "ready" for the
  user when it only exists locally; it is either published and registered, or the
  job is blocked with the exact missing step.
- Business-type research for typical apps, expected features, UX patterns, and
  look and feel.
- User-uploaded visual references for style context.
- SDD-first project structure with specs, plans, and tasks from the start.
- Auth, registration, Google login placeholders, RBAC, admin, domain CRUD
  foundations, and notifications as mandatory generated capabilities.
- Validation and doctor checks proving the created project can run.
- Persisted drafts/jobs so history survives backend restarts, with interrupted
  recovery for jobs that were running during a restart.

## Non-Goals

- Do not publish to App Store, Play Store, or AWS in the first implementation.
- Do not require Google, Apple, Play Console, GitHub, or AWS credentials to
  create a local project, but missing GitHub/release credentials must remain
  visible as publish blockers.
- Do not hardcode real passwords or secrets into generated code or committed
  files.
- Do not let demo/mock runtime behavior leak into productive releases.
- Do not overwrite an existing project folder.

## Chat-Mode Contract

The primary "New project" action creates a normal chat configured as Project
Factory mode. The first agent response asks only for decisions that cannot be
inferred and states defaults clearly:

1. Project name.
2. Business type.
3. Primary goal.
4. Platforms, defaulting to iOS, Android, and Web.
5. Optional visual reference images attached through the normal chat attachment
   tray. These references are a binding UI/UX input, not generic inspiration.
6. Logo/icon choice: upload, generate, or temporary placeholder.
7. Backend choice, defaulting to FastAPI.
8. Domain entities, user roles, key permissions, external integrations, and
   deployment assumptions needed for baseline SDD diagrams.
9. Preview and explicit confirmation before generating files.
10. History/recovery panel for persisted drafts and jobs.

If the agent does not have enough information to generate the foundation spec,
plan, tasks, and baseline diagrams, it must ask concrete simple questions with
suggested answers. Reviewer/build mode must remain disabled during this intake.
Only after the user validates a preview that covers specs, plan, tasks, domain
entities, roles/permissions, modules, component/class/entity-relationship/
deployment diagrams, risks, and validation commands may the agent emit
`PROJECT_FACTORY_READY_FOR_BUILD`. The mobile app only enables the 20 generator
+ 20 reviewer workflow after that marker exists and the user confirms.

The older form-style dialog remains an implementation component/fallback, but
the user-facing path is chat-first so the user can describe an app naturally,
attach images in the same conversation, ask the agent to infer missing name or
business type, and approve a preview before generation.

## Generated Project Shape

```text
new-project/
  .codex/project.yaml
  apps/mobile/
  backend/
  scripts/publish_project.sh
  scripts/validate_generated_project.sh
  specs/001-product-foundation/
    spec.md
    plan.md
    tasks.md
    metadata.yaml
  .sdd/
    spec-index.yaml
    diagram-index.yaml
  architecture/
    components.mmd
    components.yaml
    classes.mmd
    classes.yaml
    entity-relationship.mmd
    entity-relationship.yaml
    deployment.mmd
    deployment.yaml
  docs/research/
  design/
  assets/reference/
  infra/aws/
  release/
  AGENTS.md
  README.md
```

## Required Defaults

- Flutter targets: iOS, Android, Web.
- Backend: FastAPI unless the user selects another option.
- Creation runner: Codex CLI with generator/reviewer batches.
- Creation batch default: 20 generator runs and 20 reviewer runs.
- Auth: registration, email/password login, password reset path, session
  persistence, and Google login placeholders.
- Access control: RBAC with `owner`, `admin`, `manager`, `staff`, `customer`,
  and `guest`.
- Admin: enabled, with user, role, permission, settings, and domain management.
- Seed admin: configured only through environment variables/secrets.
- Notifications: in-app, push, and email foundations.
- Codex: Feedback Bridge, Dev Workbench, app updater, and SDD metadata enabled.
- SDD baseline diagrams: component, class, entity-relationship, and deployment
  diagrams are generated with metadata sidecars and indexed for Workbench.
- Runtime profile: `APP_RUNTIME_PROFILE=real` by default for productive
  releases; `mock` and `staging` are explicit opt-in profiles.
- Publish contract: initial git commit required, GitHub repository/push required
  before the project is considered published, Android release and APK asset
  verification required before the app is considered installable, Codex Mobile
  installable-app registration required before the app is expected to appear in
  the Apps catalog, and release status must be explicit.

## Publication Completion Contract

The Factory regression that generated `sat-showroom` exposed a gap: the job
ended as `ready` with the message `Local project foundation generated` even
though the repository had no GitHub `origin`, no remote repository, no Android
release, and no installable-app registry entry. Future Factory runs must not
close that way.

Remote publication mode must execute and verify these phases in order:

1. `scripts/finalize_local_commit.sh`
2. `scripts/publish_project.sh` to create/verify the GitHub repository and push
   the current branch.
3. `scripts/publish_android_release.sh --push --watch` to create/push the
   productive Android tag, wait for GitHub Actions, and verify APK assets.
4. `scripts/register_installable_app.sh` to register the APK with the Bridge.
5. `scripts/validate_publication_ready.sh` to prove remote, tag, release asset,
   profile, updater, and publish metadata are coherent.

If any publication phase cannot run because `gh` is unauthenticated, GitHub
permissions are missing, release secrets are absent, `BRIDGE_URL` or
`INSTALLABLE_APPS_REGISTRATION_TOKEN` is missing, or the APK asset cannot be
verified, the job status must become `blocked`. It must include the failing
phase, command, exit code, redacted stdout/stderr, and a concrete manual next
step. It must not become `ready`.

`local` publication validation mode remains only for tests and explicit local
development. It may validate local commit readiness, but it must be visibly
different from remote publication and must not be used to claim that the app is
available in Codex Mobile Apps.

## Runtime Profile Contract

Every generated project must include a central runtime profile selector:

- `APP_RUNTIME_PROFILE=real`
- `APP_RUNTIME_PROFILE=mock`
- `APP_RUNTIME_PROFILE=staging` when useful

`real` is the default for productive releases. `mock` is opt-in and is only valid
for demo/local release tags such as `android-mock-vX.Y.Z-build.N` or
`android-local-vX.Y.Z-build.N`.

Mock/demo releases are installable early-test builds. They do not require a real
backend or remote database, use local/in-memory app data, expose a visible seed
role selector, and mark release metadata with:

- `runtime_profile=mock`
- `mock_or_demo=true`
- `backend_required=false`

Productive releases use tags such as `android-vX.Y.Z-build.N` and must use a
real backend URL, real updater metadata, real auth, and no visible seed role
selector, demo data, localhost, placeholder URLs, or visible Workbench/dev
tools. Productive release metadata must include:

- `runtime_profile=real`
- `mock_or_demo=false`
- `backend_required=true`
- `API_BASE_URL=<real backend URL>`
- signing metadata, with release keystore or an explicit debug fallback status.

Generated CI and validation scripts must fail productive release builds when
they detect mock/local profiles, seeded demo selectors, hardcoded demo users,
localhost, placeholder/example URLs, updater metadata with `mock_or_demo=true`,
missing release metadata, missing APK assets, or a dirty/unpushed worktree.

## Visual Reference Contract

When the user attaches visual references, the Factory must analyze each image
before implementing UI and extract:

- screen structure, navigation, headers, cards, buttons, chips/filters, lists,
  iconography, typography, spacing, borders/radius, empty states, primary action
  position, and dashboard/inventory/catalog patterns where present.

The Factory must map those references to concrete generated screens. For
example, inventory references must influence an inventory screen, dashboard
references must influence dashboard composition, and catalog references must
influence catalog cards, filters, and navigation. A generic Flutter Material
shell, default `AppBar`, default buttons, or unstyled list is a generation
failure when references exist.

Generated projects must include design tokens derived from the references,
reusable UI components based on the visual patterns, and a visual validation
report. If the user requests a different palette, the Factory adapts color while
preserving structure, rhythm, layout, cards, navigation, and interaction
patterns.

Logo and app icon assets are treated as exact assets. If the user supplies only
a logo, it is also used as the app icon source unless overridden. If the user
supplies only an app icon, it is also used as primary brand/logo source unless
overridden. Source bytes are preserved and derived sizes are generated from that
source.

The preview before build must list detected visual references, screens derived
from each reference, final palette, reusable components, intentional
differences, and visual risks. The final report must list images used, influenced
screens, logo/icon paths, whether logo and icon share a source, generated
previews, and intentional visual differences.

## Workbench And Developer Tooling Contract

Workbench is mandatory from project creation. Generated projects must include
baseline specs, plans, tasks, diagram indexes, architecture diagrams,
`sourceApp`/workspace identity, feedback bridge configuration, and documentation
for opening and using Workbench.

Workbench and developer feedback UI may be visible in `mock` or internal
profiles, but must be hidden or disabled in productive `real` releases. If a
Workbench registration step cannot complete automatically, the Factory must
record a blocking status and an exact manual command.

## Updater And Release Contract

Every generated project must include a real updater surface from the start:

- backend endpoint such as `/app-updates/current`;
- version, build, release tag, APK URL, release URL, runtime profile, and
  `mock_or_demo` metadata;
- Flutter wiring ready to consume the feed;
- release metadata that matches the updater response.

The Factory cannot consider a project finished only because files were generated
locally. The publish contract requires an initial commit, `main` branch, GitHub
remote creation or verification with authenticated tooling, push, release tag,
GitHub release, APK asset verification, release metadata verification, and a
clean worktree or explicit blocking report.

### SAT Showroom Publication Gap

This requirement was hardened after SAT Showroom regenerated successfully as a
local foundation but did not appear in Codex Mobile Apps. The root cause was
that generated publication helpers existed, but the runner could still finish as
`ready` without owning the GitHub repo creation, Android release, and Bridge
installable-app registration phases. The fix is that remote Project Factory jobs
must execute those phases directly:

- `github_publish`: run `scripts/publish_project.sh` to create or verify the
  authenticated GitHub repo, set `origin`, normalize `main`, and push HEAD.
- `android_release`: run `scripts/publish_android_release.sh` to validate real
  release configuration, push the productive Android tag, wait for the GitHub
  release APK asset, and reject mock/local release settings.
- `installable_app_registration`: run `scripts/register_installable_app.sh` to
  register the verified APK in the Bridge catalog.
- `publish_verification`: run `scripts/validate_publication_ready.sh` after the
  previous phases so the final job state reflects the actual installable app.

If external configuration is missing, such as `gh` auth, `API_BASE_URL`,
`BRIDGE_URL`, or `INSTALLABLE_APPS_REGISTRATION_TOKEN`, the job must end as
`blocked` with the exact phase and command in `step_logs`, not as `ready`.

After an APK release is published, the generated project must register itself in
the Bridge installable-app catalog through the protected Bridge endpoint
`POST /installable-apps`. The Bridge must require
`INSTALLABLE_APPS_REGISTRATION_TOKEN` and must keep install URLs routed through
Bridge APK proxy endpoints rather than accepting arbitrary external APK URLs.
The generated `scripts/register_installable_app.sh` must verify the GitHub
release asset first, send the registration token by header, then confirm
`GET /installable-apps/{sourceApp}` returns an installable APK proxy URL.

## Implemented API Surface

- `GET /project-factory/options`
- `GET /project-factory/doctor`
- `POST /project-factory/drafts`
- `GET /project-factory/drafts`
- `GET /project-factory/drafts/{id}`
- `POST /project-factory/drafts/{id}/dry-run`
- `POST /project-factory/drafts/{id}/reference-assets`
- `GET /project-factory/drafts/{id}/reference-assets`
- `DELETE /project-factory/drafts/{id}/reference-assets/{asset_id}`
- `POST /project-factory/drafts/{id}/generate`
- `GET /project-factory/jobs`
- `GET /project-factory/jobs/{id}`

`GET /project-factory/jobs` supports `status`, `draft_id`, and `limit`.
Completed jobs expose `project_path`/`target_path` for workspace refresh and
open actions. Failed, blocked, and interrupted jobs expose error summaries and a
manual next step; retry is intentionally not implemented because generation is
not yet safely reversible.

## Persistence And Recovery

Drafts and jobs are persisted under `PROJECT_FACTORY_STATE_DIR`. Reference
assets are persisted under `PROJECT_FACTORY_REFERENCE_ASSET_DIR`.

On backend startup, persisted `queued` or `running` jobs are recovered as
`interrupted` with a clear error and a recovery log entry. The mobile app treats
`interrupted` as a terminal state and exposes it in Project Factory History.

## Generated Templates

The generated backend is a runnable FastAPI v1 template with:

- SQLite `DATABASE_URL`;
- env-only admin seed;
- email/password auth;
- JWT-compatible HS256 tokens;
- RBAC roles;
- admin users/roles/domains endpoints;
- Google auth pending-credential endpoint;
- notification list/read endpoints;
- generated tests.

The generated Flutter app is a runnable template with:

- `API_BASE_URL` required by `--dart-define`;
- `APP_RUNTIME_PROFILE`, defaulting to `real`;
- mock profile support with local/in-memory data and a role seed selector;
- login/register/session in memory;
- admin gating by RBAC;
- domain/user admin views;
- notification list/read flow;
- generated tests.

The generated project includes `scripts/validate_generated_project.sh`, which
installs/prepares the generated backend, runs backend tests, starts FastAPI on a
local port, validates auth/admin/notifications via real HTTP, and runs generated
Flutter tests against that backend when Flutter is available.

The generated project also includes `scripts/publish_project.sh`, which creates
or verifies the GitHub repository through authenticated `gh`, pushes the main
branch, and reports the remote URL. Project Factory creates the initial local
commit itself so a generated repo never remains in `No commits yet` state.

The generated project also includes `scripts/publish_android_release.sh`, which
derives the productive Android tag from `apps/mobile/pubspec.yaml`, validates
`APP_RUNTIME_PROFILE=real` plus a non-local `API_BASE_URL`, pushes the tag, and
waits for the GitHub release to expose an APK asset. The Android workflow copies
the built APK to a stable `<sourceApp>.apk` asset name so Bridge registration can
verify the exact installable artifact.

## Completion Criteria

A project is not considered created until the backend returns a validation
report showing:

- manifest valid;
- project files created inside `PROJECTS_ROOT`;
- initial local git commit exists and the worktree is clean after scaffold;
- GitHub repo/push is complete or explicitly blocked with a credential/config
  reason and manual next step;
- Android release tag and APK asset are complete or explicitly blocked with a
  credential/config reason and manual next step;
- Bridge installable-app registration is complete or explicitly blocked with a
  credential/config reason and manual next step;
- release profile checks pass for productive and mock/demo tags;
- productive release checks prove no mock/local/demo mode, localhost,
  placeholder URL, visible seed selector, or visible Workbench tooling is active;
- Flutter dependencies resolve;
- Flutter tests pass when tooling is available;
- backend health/tests pass when tooling is available;
- admin seed is configured by env names only;
- Google login is present and marked `pending_credentials` when credentials are
  absent;
- Workbench can discover the project;
- Feedback Bridge, Workbench, and updater are integrated or represented as
  explicit verified blockers with exact commands;
- no secrets are written to committed files.

The final Factory report must include commit hash, repo URL, branch, mock/demo
release tag if generated, productive release tag if generated, APK URLs, runtime
profile and `mock_or_demo` status for each release, backend URL, updater
response, Workbench status, tests executed, and real blockers.
