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
- Optional GitHub repository creation is deferred; local git initialization is
  included and remote credentials remain pending.
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
  create a local project.
- Do not hardcode real passwords or secrets into generated code or committed
  files.
- Do not generate demo/mock release builds unless explicitly requested.
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
   tray.
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
- Release data mode: real by default.

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
- login/register/session in memory;
- admin gating by RBAC;
- domain/user admin views;
- notification list/read flow;
- generated tests.

The generated project includes `scripts/validate_generated_project.sh`, which
installs/prepares the generated backend, runs backend tests, starts FastAPI on a
local port, validates auth/admin/notifications via real HTTP, and runs generated
Flutter tests against that backend when Flutter is available.

## Completion Criteria

A project is not considered created until the backend returns a validation
report showing:

- manifest valid;
- project files created inside `PROJECTS_ROOT`;
- Flutter dependencies resolve;
- Flutter tests pass when tooling is available;
- backend health/tests pass when tooling is available;
- admin seed is configured by env names only;
- Google login is present and marked `pending_credentials` when credentials are
  absent;
- Workbench can discover the project;
- Feedback Bridge and updater remain required follow-up work in generated SDD
  tasks until their concrete packages are wired into the template;
- no secrets are written to committed files.
