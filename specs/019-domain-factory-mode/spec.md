# Domain Factory Mode

id: 019-domain-factory-mode
status: partial
owner: codex-mobile-bridge

## Intent

Add a Domain Factory mode that starts from a project already created by New
Project deterministic init. Domain Factory is not another project creator. It is
the product/domain work mode for an initialized project.

The user should be able to open a project chat such as `prueba-17`, tap Domain
Factory, describe the real business domain, attach visual references or assets,
answer follow-up questions, and then have generator/reviewer implement the
domain layer on top of the existing baseline. The work must end in a new real
preview release and installable APK when the project strategy supports Android.

This spec complements:

- `005-new-project-factory`
- `007-initial-preview-release`
- `011-new-project-guided-intake`
- `013-workbench-kanban-curator`
- `017-new-project-deterministic-init-pipeline`

## Product Outcome

When the user taps Domain Factory from an initialized project chat:

- the app keeps the user inside the current project;
- the backend identifies the current workspace and source app;
- the system reads the deterministic baseline context from generated project
  files;
- the current chat is configured for Domain Factory generator/reviewer mode;
- the first Domain Factory message tells the agents where they are standing and
  what already exists;
- the user can send a long business/domain brief plus images or references;
- the system asks only the missing domain questions;
- the domain contract covers business entities, roles, permissions, workflows,
  visual direction, screens, backend behavior, data model, integrations, and
  release expectations;
- generator and reviewer work in paired passes after domain intake is clear;
- generator/reviewer may modify the product broadly, including UI, colors,
  layout, navigation, backend domain code, data models, tests, specs, diagrams,
  and release files;
- generator/reviewer must not recreate baseline infrastructure;
- the generic admin/auth/RBAC foundation remains intact;
- domain-specific roles and permissions are generated as needed, while owner or
  admin retains access to everything;
- the work produces or updates SDD spec, plan, tasks, traceability, DER/ERD,
  class, sequence, component, and deployment diagrams;
- the work finishes with a new real preview release, updated APK metadata, and
  Bridge installable discovery for installable projects.

## Core Rules

- Domain Factory is project-scoped. It acts on the current chat/workspace, not a
  new workspace.
- Domain Factory starts only after New Project deterministic init has produced a
  baseline context or a user-visible blocked-with-context baseline.
- Domain Factory must not create a new repo, new project slug, new baseline
  preview, or new initial release.
- Domain Factory must not switch to mock/demo/local/placeholder data unless the
  user explicitly asks for that.
- Domain Factory must keep preview runtime real:
  `APP_RUNTIME_PROFILE=preview`, `API_RUNTIME=cloudflare_preview`, and the
  preview API at `https://preview.nienfos.com/{slug}/api`.
- Domain Factory may modify product surfaces broadly: visuals, colors, layout,
  screens, state, domain backend, migrations, tests, specs, and release scripts.
- Domain Factory must preserve generic admin/auth/RBAC foundation behavior.
- Domain Factory may add domain-specific admin modules, role-management records,
  permissions, screens, and seed data when the business domain requires them.
- Owner/admin must retain access to all domain capabilities.
- Domain roles are domain-owned and inferred from requirements, examples:
  employee, customer, contractor, cook, guest, supplier, driver, manager,
  operator, vendor, patient, teacher, student, tenant, landlord.
- Domain role permissions must be explicit and testable.
- Visual implementation is first-class. The agents must prioritize the real
  product look and feel, visual hierarchy, navigation, empty states, mobile
  ergonomics, and reference-image fidelity.
- Every Domain Factory run must update SDD evidence before claiming readiness.
- Every Domain Factory implementation run must publish a new preview release
  unless the user explicitly stops before release.
- Remote side effects must be auditable: commits, tags, releases, APK checksum,
  preview URL, smoke evidence, and Bridge registration must be recorded.
- Secrets must not be written to generated projects, chat prompts, logs, specs,
  or release evidence.

## Baseline Context Contract

The backend must build a deterministic Domain Factory context from the current
project before configuring agents.

Required sources, when present:

- `codex-bridge.yaml`
- `.codex/factory/init-result.json`
- `.codex/factory/llm-start-context.md`
- `release/preview-runtime.json`
- `.codex/project.yaml`
- current SDD project summary and spec tree
- current installable-app registry detail
- current Git repository HEAD, branch, remote, tags, and latest release metadata

The context must include:

- source app and display name;
- workspace path;
- chat/session id;
- GitHub repo and branch;
- current commit;
- preview URL and API URL;
- runtime profile and API runtime;
- APK/installable status and latest build number;
- Workbench/SDD status;
- feedback/updater status;
- known baseline files and protected foundation areas;
- first spec/baseline summary;
- existing unresolved blockers;
- explicit instructions for generator/reviewer.

## Domain Intake Contract

Domain Factory intake collects only domain/product information, not baseline
infrastructure information.

It should ask about:

- business domain and primary outcome;
- core user groups and domain roles;
- role permissions and owner/admin override expectations;
- domain entities and relationships;
- primary workflows;
- data that must be persisted;
- admin modules that belong to the domain;
- notifications and business events;
- integrations;
- visual identity, style, colors, and reference images;
- screens/navigation;
- mobile-first behavior and empty states;
- release acceptance criteria.

It must not ask again for:

- project name or slug, unless the user explicitly wants a rename later;
- frontend strategy;
- backend framework;
- GitHub repo;
- Cloudflare preview setup;
- D1 baseline identity;
- initial admin emails;
- initial APK/release setup;
- Bridge installable setup;
- Workbench setup.

## Agent Mode Contract

Domain Factory configures both generator and reviewer.

Generator must:

- consume the baseline context before editing;
- implement business/domain behavior, not baseline project plumbing;
- preserve generic admin/auth/RBAC infrastructure;
- add domain roles and permissions required by the business;
- keep owner/admin as all-access;
- prioritize visual implementation and reference-image fidelity;
- update domain model, UI, backend, migrations, tests, SDD artifacts, and
  release evidence;
- finish by producing a new real preview build/release when implementation work
  starts.

Reviewer must:

- review with the same baseline context;
- verify the generator did not recreate baseline infrastructure;
- verify admin/auth/RBAC foundation remains intact;
- verify domain roles and permissions match the requested business;
- verify owner/admin all-access behavior;
- verify visual quality and mobile ergonomics;
- verify backend/domain behavior, persistence, and migrations;
- verify SDD spec, plan, tasks, DER/ERD, class, sequence, component, and
  deployment diagrams are updated;
- verify tests and preview/release evidence;
- produce actionable next prompts until the release is ready.

## Domain Implementation Scope

Domain Factory may touch:

- generated project Flutter UI and web surfaces;
- generated backend domain code;
- domain database migrations;
- domain services and repositories;
- domain-specific admin screens;
- design tokens and assets;
- app icon/logo if the user provides or approves changes;
- tests;
- specs, plan, tasks, diagrams, traceability;
- release scripts and evidence needed for the next preview release.

Domain Factory should avoid touching:

- generic auth flow unless domain requirements require a compatible extension;
- generic RBAC engine internals unless domain roles cannot be represented;
- Bridge installable plumbing except to publish/register the next build;
- Workbench plumbing except to keep it discoverable;
- Project Factory deterministic init code from inside generated projects;
- mock/demo switches unless requested.

## Release Contract

Once Domain Factory begins implementation, the normal completion target is:

- clean working tree or deliberate committed changes;
- updated SDD artifacts;
- passing relevant tests;
- preview smoke passes;
- new Android preview APK for Flutter/installable projects;
- new GitHub prerelease tag after the initial build;
- Bridge installable registry points to the new build;
- app updater sees the new build from previous preview APKs;
- release evidence is written and shown to the user.

The system may block before release only when:

- credentials or external services are unavailable;
- tests fail;
- preview smoke fails;
- APK build/signing fails;
- Bridge registration fails;
- the user explicitly pauses or requests no release.

Blocked states must include exact phase, failure, evidence, blast radius, and
next safe action.

## UI Contract

The mobile app should add a Domain Factory entry near New Project.

Initial version:

- show Domain Factory below New Project in the project menu;
- require a current project/session;
- configure the current chat rather than creating a new project;
- show a short confirmation that the project is entering Domain Factory mode;
- allow the user to type or paste a long domain brief;
- keep attachment/reference support available;
- show Domain Factory state in chat;
- do not expose project-creation fields.

Later versions may add a richer dialog, but the first version should optimize
for starting the domain conversation quickly.

## Operational Governance

Safe defaults:

- local prompt/config changes are safe;
- dry-run context generation is safe;
- SDD spec creation inside the selected workspace is safe after user action;
- release publication requires successful tests and release checks.

Requires human approval:

- force-push, tag deletion, or release deletion;
- production release;
- deleting repositories, workspaces, D1 databases, Workers, or routes;
- switching a real preview build to mock/demo;
- changing global admin/auth/RBAC semantics.

Rollback:

- agent configuration changes can be reverted by restoring prior session config;
- project code changes must be reverted by git commit/branch/tag strategy;
- failed releases must preserve evidence and avoid deleting old installable
  builds unless explicitly approved;
- Bridge installable registry can be repointed to the previous build with
  explicit approval.

## Implementation Status

Implemented and tested in the bridge:

- backend Domain Factory context builder and activation route for the current
  session only;
- strict critical baseline validation for `codex-bridge.yaml`,
  `.codex/factory/init-result.json`,
  `.codex/factory/llm-start-context.md`, `release/preview-runtime.json`, and
  `.codex/project.yaml`;
- strict preview runtime validation requiring `preview`,
  `cloudflare_preview`, and `https://preview.nienfos.com/{slug}/api`;
- current-session generator/reviewer configuration with protected foundation
  areas, allowed domain modification areas, destructive-operation approval
  policy, domain intake fields, role/permission model, follow-up question
  template, and release guardrails;
- mobile Domain Factory entry next to New Project, gated on current session;
- SDD bootstrap per Domain Factory run, including spec/plan/tasks/
  traceability, intake contract JSON, media-reference placeholder, release
  guardrails JSON, and DER/ERD, class, sequence, component, and deployment
  diagram templates.
- intake submission for the current session, writing the original brief and
  media references under the generated Domain Factory SDD intake directory;
- contract preview generation/persistence before implementation, including
  roles, permissions, owner/admin all-access, entities, relationships,
  workflows, screens, visual direction, backend scope, tests, diagram updates,
  and release target;
- transition from intake to implementation-ready and implementing state with
  generator/reviewer paired workflow evidence;
- completion evidence enforcement so Domain Factory tasks cannot be considered
  complete without implementation, validation, and release or real blocked
  release evidence;
- concrete release evidence validator for build increment after build 1, real
  preview runtime/API, no mock/demo/local/placeholder values, and required
  release evidence fields.

Still pending:

- Android/GitHub/Bridge/updater preview release execution;
- persisted real release evidence from an actual approved preview release.

## Evidence

- `python3 -m py_compile backend/app/application/services/domain_factory_service.py backend/app/api/routes.py backend/app/api/schemas.py backend/app/container.py`
- `uv run ruff check backend/app/application/services/domain_factory_service.py tests/test_domain_factory_service.py`
- `uv run pytest tests/test_domain_factory_service.py -q` (`11 passed`)
- `flutter test test/api_client_test.dart --plain-name "api client starts domain factory on current session"`
- `flutter test test/api_client_test.dart --plain-name "api client submits domain factory intake and confirms implementation"`
- `flutter test test/api_client_test.dart --plain-name "server metadata exposes project factory capability"`
- `flutter test test/chat_screen_overflow_test.dart --plain-name "domain factory action starts on the current chat"`
