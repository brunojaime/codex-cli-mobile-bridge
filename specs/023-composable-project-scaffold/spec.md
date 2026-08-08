---
id: 023-composable-project-scaffold
title: Composable Project Scaffold
status: completed
type: feature
domains:
  - project-factory
  - scaffold
  - react-native
  - flutter
  - sveltekit
  - fastapi
  - go
  - cloudflare
  - aws
  - terraform
  - workbench
  - android-release
related_specs:
  - 005-new-project-factory
  - 011-new-project-guided-intake
  - 014-project-factory-frontend-strategy
  - 017-new-project-deterministic-init-pipeline
  - 019-domain-factory-mode
  - 021-ux-agent-lane
  - 022-project-charter-documentation-framework
---

# Composable Project Scaffold

## Intent

Extend New Project with a first-class `scaffold` creation mode and replace the
current monolithic frontend strategy with independent mobile, web, API,
infrastructure, and artifact providers.

Scaffold mode asks only the minimum technical questions and creates a real,
buildable, recoverable project foundation. It may create the local workspace,
GitHub repository, Workbench/SDD metadata, CI, a neutral Cloudflare preview,
and optional AWS Terraform readiness. It must not infer or implement product
UX, domain behavior, navigation, visual identity, business data, or a release
APK by default.

The same provider model must support:

- Flutter or React Native with Expo for mobile;
- Flutter Web, SvelteKit, or no web target;
- FastAPI, Go, or no API target;
- Cloudflare as the initial web/edge provider;
- optional AWS Terraform readiness without applying cost-bearing resources;
- framework-neutral Android APK publication and Bridge registration after
  product implementation requests it.

This spec creates the technical foundation on which later Domain Factory and UX
work operate. It does not replace Domain Factory. It gives the user a deliberate
stop point between “the project exists” and “start building the product”.

## Product Outcome

When the user chooses **New Project → Scaffold**:

- the app asks only for project identity and technical stack decisions that
  cannot be inferred safely;
- the backend creates a versioned Project Factory manifest with independent
  targets;
- a resumable deterministic scaffold pipeline creates the workspace;
- selected framework bootstraps compile and validate, but expose only a neutral
  technical shell;
- the GitHub repository is created or verified and the initial commit is
  pushed when GitHub publication is configured;
- Workbench discovers the repository and its infrastructure-only SDD package;
- Cloudflare may publish an operational “Scaffold ready” page and health
  evidence without claiming that the product or API is ready;
- optional AWS Terraform files are generated and validated but never applied
  automatically;
- no Domain Factory, UX lane, product generator/reviewer loop, APK publication,
  or product preview begins automatically;
- the project reaches the explicit terminal state `scaffold_ready`;
- the user can open the workspace immediately and later choose **Start
  product**, which launches Domain Factory against the same repository and
  infrastructure context.

When the user chooses the existing product creation path, Project Factory uses
the same composable target/provider model while preserving the current real-data
preview and release guardrails.

## Terminology

### Creation mode

`creation.mode` defines how far New Project is authorized to proceed:

- `scaffold`: create and validate the technical foundation, then stop;
- `product`: continue through product/domain intake and the existing product
  implementation lifecycle.

This is a creation mode, not an app version, manifest version, runtime profile,
or release channel.

### Technical bootstrap

A technical bootstrap is the smallest compilable implementation needed to
prove the selected toolchain. It may show a neutral `Scaffold ready` status and
provide a health check. It must not establish product navigation, screens,
colors, branding, domain entities, roles, workflows, or data.

### Product implementation

Product implementation begins only after an explicit user action from a
`scaffold_ready` project. Domain Factory and the UX lane then own information
architecture, visual direction, screens, domain behavior, persistence, and
release acceptance.

### Target provider

A target provider owns one technical target and implements a common lifecycle:

- plan;
- scaffold;
- validate;
- describe runtime configuration;
- describe release capabilities;
- report artifacts and blockers.

Providers must not own unrelated targets or infer capabilities from framework
names outside the provider registry.

## Core Rules

- Scaffold mode must never silently become product mode.
- Scaffold mode must never start Domain Factory or the UX lane automatically.
- Scaffold mode must not ask for business type, primary workflows, entities,
  roles, screens, navigation, colors, logo, or visual references.
- Scaffold mode must create a buildable technical baseline for each selected
  code target unless the user explicitly chooses metadata-only generation.
- A technical bootstrap must be visually neutral and clearly non-product.
- Scaffold mode must not generate auth, RBAC, admin, notifications, business
  records, seed users, domain migrations, or mock/demo product data.
- Scaffold mode must not publish an Android APK by default.
- Producing a temporary local build artifact during validation is allowed; it
  must not be registered, released, or described as an installable product.
- `scaffold_ready` means the requested scaffold contract is satisfied. It does
  not mean `preview_ready`, `product_ready`, `production_ready`, or
  `installable`.
- Missing credentials block only the affected remote phase and must preserve a
  usable local scaffold plus exact recovery instructions.
- Product and scaffold artifacts must never contain secrets.
- Runtime profile names remain `preview`, `staging`, `real`, and explicit
  `mock`; scaffold state is not a runtime profile.
- The real-data release policy remains unchanged: no release may use mock,
  seeded, localhost, placeholder, or example data unless the user explicitly
  requested a mock/demo release.
- Existing manifest v1 drafts, jobs, generated projects, and release histories
  must remain readable and resumable.
- Existing Flutter projects must not be migrated implicitly.
- Target selection and declared capabilities must be persisted before files or
  remote resources are created.
- Capabilities must be derived from provider contracts and verified artifacts,
  never from optimistic UI assumptions.

## Minimal Scaffold Intake

The default scaffold intake asks, in order:

1. **Project name**
   - derive a safe slug and allow review;
   - reuse configured GitHub owner and projects root when available.
2. **Stack preset**
   - `react-native-expo + sveltekit + fastapi` (recommended);
   - `react-native-expo + sveltekit + go`;
   - `flutter + sveltekit + fastapi`;
   - `flutter + sveltekit + go`;
   - `sveltekit + fastapi/go` web-only;
   - custom independent targets.
3. **Cloudflare setup**
   - `provision_scaffold` (recommended when credentials exist);
   - `generate_only`;
   - `disabled`.
4. **AWS readiness**
   - `none` (default);
   - `terraform_ready`;
   - `architecture_docs_only`.
5. **GitHub target**, only if owner, visibility, or repository destination
   cannot be inferred safely.
6. **Initial administrator email**, only when the selected scaffold preview is
   explicitly protected by the existing invite/access system.

The app must summarize the resolved stack, remote effects, skipped product
work, and expected `scaffold_ready` outputs before confirmation.

## Manifest V2 Contract

New composable projects use `.codex/project.yaml` schema version 2.

```yaml
schema_version: 2

creation:
  mode: scaffold
  auto_start_domain_factory: false
  bootstrap_level: buildable

project:
  name: Example
  slug: example

targets:
  mobile:
    enabled: true
    provider: react_native_expo
    platforms: [android, ios]
    source_root: apps/mobile

  web:
    enabled: true
    provider: sveltekit
    source_root: apps/web

  api:
    enabled: true
    provider: fastapi
    source_root: services/api
    deployment_status: prepared

infrastructure:
  web_edge:
    provider: cloudflare
    mode: provision_scaffold
    d1: false
  aws:
    mode: terraform_ready
    apply: false

artifacts:
  android:
    provider: gradle_apk
    publish_during_scaffold: false

lifecycle:
  state: scaffold_initializing
  next_action: start_product
```

### V1 compatibility mapping

Manifest v1 remains supported through an in-memory compatibility adapter:

- `frontend_strategy=flutter` maps to Flutter mobile plus Flutter Web;
- `frontend_strategy=svelte` maps to no mobile target plus Svelte web;
- `backend=fastapi|go|none` maps to the API target, while legacy generated
  output continues to be interpreted according to its recorded artifacts;
- missing `creation.mode` maps to `product` for existing projects;
- existing phase names and payload aliases remain readable until a separate
  breaking API version is approved.

The migration adapter must not rewrite existing project manifests merely by
reading them.

## Provider Registry Contract

Each provider declares stable metadata and implements a common contract.

```yaml
id: react_native_expo
target_kind: mobile
source_root: apps/mobile
capabilities:
  android: true
  ios: true
  web: false
  local_validation: true
  android_apk: true
  bridge_installable: true
  product_feedback_adapter: true
  product_updater_adapter: true
required_tools: [node, npm, java]
```

Provider operations:

```text
plan(context) -> TargetPlan
scaffold(context, plan) -> TargetScaffoldResult
validate(context, plan) -> TargetValidationResult
runtime_contract(context) -> RuntimeContract
release_contract(context) -> ReleaseContract
doctor(context) -> ProviderDoctorResult
```

Provider results must contain:

- provider and target id;
- executed commands with redacted evidence;
- generated files;
- tool versions;
- capabilities promised and verified;
- local artifacts;
- remote artifacts;
- blockers and exact next actions;
- content/config hashes needed for idempotency.

The first provider set is:

- mobile: `flutter`, `react_native_expo`, `none`;
- web: `flutter_web`, `sveltekit`, `none`;
- API: `fastapi`, `go`, `none`;
- web/edge: `cloudflare`, `none`;
- AWS readiness: `terraform_ready`, `architecture_docs_only`, `none`;
- Android artifact: `gradle_apk` with framework-specific build adapters.

## Generated Scaffold Shape

```text
project/
  .codex/
    project.yaml
    factory/
      scaffold-result.json
      scaffold-context.md
  .sdd/
    spec-index.yaml
    diagram-index.yaml
  apps/
    mobile/                       # when selected
    web/                          # when selected
  services/
    api/                          # when selected
  contracts/
    openapi.yaml
    runtime.schema.json
  infra/
    cloudflare/                   # generate/provision contract
    aws/                          # optional Terraform readiness
  specs/
    000-project-scaffold/
      spec.md
      plan.md
      tasks.md
      traceability.yaml
      metadata.yaml
  release/
    scaffold-status.json
    runtime-profiles.md
    release-contracts.yaml
  scripts/
    validate_scaffold.sh
    doctor_scaffold.sh
    build_targets.sh
  .github/workflows/
    scaffold-validation.yml
  codex-bridge.yaml
  AGENTS.md
  README.md
```

The infrastructure SDD package records only technical decisions, selected
providers, validation evidence, remote resources, blockers, and the explicit
absence of product decisions.

Project Charter generation from spec 022 must be mode-aware. Scaffold mode may
create a minimal technical charter/index containing project identity, creation
mode, stack, infrastructure posture, and pending product definition. It must not
invent product objective, benefits, scope, brand, or client-facing claims.

## Scaffold State Machine

Stable states:

- `draft`;
- `scaffold_contract_ready`;
- `scaffold_initializing`;
- `scaffold_blocked_with_context`;
- `scaffold_ready`;
- `domain_intake`;
- `product_foundation`;
- `preview_ready`.

`scaffold_ready` is terminal for the scaffold job. Starting product work creates
or activates a distinct Domain Factory run linked to the same workspace. It does
not reopen or mutate a completed scaffold job except to add relationship
metadata.

## Deterministic Scaffold Pipeline

The scaffold runner is resumable and idempotent by phase:

1. `scaffold_preflight`
   - resolve projects root, provider registry, local tools, GitHub configuration,
     Cloudflare configuration, and Terraform availability;
   - report remote blockers before remote writes.
2. `scaffold_contract`
   - persist mode, stack, infrastructure choices, slug, capability matrix, and
     explicit skipped product work.
3. `workspace_baseline`
   - create repository structure, manifest, AGENTS, Workbench/SDD metadata,
     contracts, CI, scripts, and infrastructure-only spec.
4. `target_bootstrap`
   - invoke selected mobile, web, and API providers;
   - create only neutral technical bootstraps.
5. `target_validation`
   - install locked dependencies and execute framework tests, lint/analyze,
     type checks, builds, API contract checks, and secret/placeholder guards.
6. `local_git_commit`
   - initialize or verify git and create a clean baseline commit.
7. `github_repository`
   - create or verify the repository, configure origin, push the branch, and
     persist evidence when authorized/configured.
8. `cloudflare_scaffold`
   - generate or provision the neutral preview according to the selected mode;
   - never claim product/API readiness.
9. `aws_readiness`
   - generate docs or Terraform skeleton;
   - run format/validate where possible;
   - never run `terraform apply`.
10. `workbench_registration`
    - verify source app identity, SDD discovery, project documents, and workspace
      routing.
11. `scaffold_context_pack`
    - write structured and human-readable result files;
    - attach the result to the chat;
    - mark `scaffold_ready` or `scaffold_blocked_with_context`.

The existing deterministic init API may expose compatibility aliases for old
phase names, but new UI must render the scaffold-specific phase names.

## Neutral Bootstrap Requirements

Every enabled code target must be buildable and minimal.

Allowed:

- framework entry point;
- dependency lockfile;
- runtime configuration reader;
- source app identity;
- health/config diagnostics;
- neutral scaffold status screen;
- API `/health` endpoint;
- provider-specific smoke tests.

Forbidden before product start:

- product tabs, drawer, sidebar, or navigation hierarchy;
- dashboard, inventory, catalog, booking, admin, or other business screens;
- auth/RBAC UI and backend unless separately requested after scaffold;
- seeded users, roles, business records, or demo data;
- product colors, design tokens, logo, icon, illustrations, or copy;
- inferred entities, migrations, workflows, notifications, or integrations;
- product analytics or marketing metadata;
- published APK or installable app registration.

## React Native With Expo Provider

`react_native_expo` is the recommended mobile provider for new composable
projects.

It must:

- create a pinned Expo/React Native TypeScript project under `apps/mobile`;
- use Expo Router only for the minimum root/technical route during scaffold;
- keep product route groups absent until product work starts;
- generate Android native sources deterministically with Expo prebuild or a
  pinned equivalent process;
- keep signing secrets outside the repository;
- support local/GitHub Actions Android release builds after product mode;
- map logical runtime values to Expo public configuration without exposing
  secrets;
- support package id, semantic version, integer build, source app, and release
  tag metadata;
- provide a reusable React Native Bridge adapter for feedback, Workbench launch,
  and updater behavior in product mode;
- keep Workbench Bridge-owned rather than inserting Workbench into product
  navigation;
- validate that a scaffold build contains no product/demo data and is not
  registered as installable.

EAS may be supported as an optional build executor. GitHub Actions plus the
generated Android/Gradle project remains the baseline path so Bridge release
registration does not depend on an EAS-hosted artifact.

## SvelteKit Provider

`sveltekit` replaces the current minimal Svelte/Vite path for new manifest v2
projects.

It must:

- create a pinned TypeScript SvelteKit project under `apps/web`;
- use the Cloudflare adapter or static adapter selected by the deployment plan;
- expose only a neutral scaffold route during scaffold mode;
- map logical runtime values to public SvelteKit configuration;
- include lint, typecheck, unit test, build, and preview validation commands;
- generate Cloudflare-compatible build output;
- avoid sharing React Native UI components;
- consume shared OpenAPI types, validation rules, permissions, and design tokens
  only after those artifacts exist;
- never claim Android installability.

## API Provider And Contract Parity

`contracts/openapi.yaml` is the source of truth for client/server compatibility.
In scaffold mode it contains only the common technical contract, initially
`GET /health`, error shape, correlation id, and version metadata.

FastAPI and Go providers must:

- implement the same OpenAPI operations and response semantics;
- generate framework-native project files and locked/reproducible dependencies;
- pass the same black-box conformance suite;
- expose a real local health endpoint during validation;
- avoid generating auth, RBAC, admin, notifications, or domain persistence in
  scaffold mode;
- keep runtime configuration and secrets outside source control;
- declare deployment status honestly (`prepared`, `deployed`, or `blocked`);
- never claim that a Cloudflare Worker/D1 implementation is FastAPI or Go.

Go advertised in Project Factory options must correspond to real Go source,
tests, build commands, and runtime evidence. The current behavior where Go can
be selected while FastAPI files are generated is a release blocker for this
spec.

Client code should be generated or checked from OpenAPI so React Native and
SvelteKit consume the same DTO and error contract. Shared UI is explicitly out
of scope.

## Cloudflare Scaffold Contract

Cloudflare modes:

- `provision_scaffold`: create/verify the project-scoped Worker/assets route and
  publish a neutral scaffold status page;
- `generate_only`: write manifests, Wrangler config examples, scripts, and
  validation without remote writes;
- `disabled`: record that no Cloudflare preview was requested.

Default scaffold Cloudflare behavior:

```yaml
web_preview: true
api_ready: false
d1: false
product_ready: false
production_ready: false
mock_or_demo: false
```

The neutral preview is an operational artifact, not product UX. If no web target
exists, an infrastructure-owned static status page may be deployed. The result
must not publish an API base URL unless a real selected API provider has been
deployed and verified.

D1 is opt-in after a persistence decision. Scaffold creation must not create D1
merely because Cloudflare is enabled.

## AWS Terraform Readiness Contract

AWS readiness modes:

- `none`: no AWS artifacts;
- `architecture_docs_only`: record decision points without Terraform;
- `terraform_ready`: generate a validated, resource-neutral Terraform
  foundation.

`terraform_ready` includes:

- pinned Terraform and AWS provider constraints;
- environment layout;
- project/owner/environment tags;
- variables and outputs;
- backend/state bootstrap documentation;
- empty or disabled resource modules with explicit decision gates;
- `terraform fmt -check` and `terraform validate` evidence when Terraform is
  available.

It must not:

- run `terraform apply`;
- create a state bucket, lock table, IAM principal, VPC, database, compute,
  storage, DNS, certificate, or other billable resource;
- commit credentials, account ids, secrets, or generated state;
- choose ECS, App Runner, Lambda, RDS, or another product architecture before
  product/deployment requirements exist.

Any later apply requires a separate explicit user action, resolved account and
region, a reviewed plan, cost/security posture, and the normal destructive/
external side-effect approval rules.

## Framework-Neutral Android Artifact Contract

Bridge already consumes an Android artifact contract rather than Flutter
source. Project Factory must align its release pipeline with that boundary.

Normalized artifact:

```yaml
kind: android_apk
source_app: example
framework: react_native_expo
package_id: com.example.app
version: 0.1.0
build: 1
release_tag: android-preview-v0.1.0-build.1
asset_name: example.apk
sha256: <digest>
signing_status: verified
runtime_profile: preview
mock_or_demo: false
```

The Android release service must obtain version, build command, output path, and
framework validation through provider adapters. It must not read Flutter
`pubspec.yaml` or invoke Flutter commands for a React Native target.

Scaffold default is `publish_during_scaffold=false`. Android publication and
Bridge registration become available only after explicit product/release intent
and the real preview runtime guardrails pass.

## Bridge, Workbench, Feedback, And Updater

Workbench is repository/workspace infrastructure and is required in scaffold
mode:

- `codex-bridge.yaml` exists;
- source app identity is stable;
- `.sdd` indexes are valid;
- the scaffold spec is visible;
- the Bridge can open the workspace.

Product feedback and updater integrations are capability contracts during
scaffold. Full in-app UI/wiring begins with product mode because scaffold mode
does not own product navigation or product UI.

The React Native Bridge package must eventually provide parity with the reusable
Flutter integrations:

- source app identity;
- screenshot/comment/bounds and optional audio capture;
- local queue and batch send;
- Workbench launcher/deep link owned by Bridge;
- update check, download, checksum, and Android install handoff;
- runtime visibility guardrails.

Absence of product-mode feedback/updater wiring must not block
`scaffold_ready`; it must be recorded as `prepared` or `pending_product_start`.

## Start Product Transition

From a `scaffold_ready` workspace the app exposes **Start product**.

The transition must:

- reuse the same repository, workspace, source app, manifest, Cloudflare
  resources, GitHub remote, and Workbench scope;
- create a new Domain Factory run related to the scaffold result;
- read the selected target providers and infrastructure posture;
- ask domain/UX questions that were intentionally skipped;
- avoid recreating or renaming technical foundation resources;
- add product auth, roles, domain persistence, screens, navigation, design,
  feedback/updater integration, and release work only from the approved product
  contract;
- require a real backend deployment decision before claiming API/preview
  readiness;
- publish APK/installable artifacts only after product acceptance and release
  validation.

The transition must be user-triggered. Merely opening the project or sending an
unrelated chat message does not authorize Domain Factory.

## API Contract

Project Factory APIs must expose:

- creation mode and supported modes in options;
- independent target/provider options and presets;
- infrastructure modes;
- resolved capability matrix;
- scaffold draft/contract preview;
- start/resume scaffold job;
- scaffold job status and phases;
- scaffold result/context pack;
- explicit `start-product` transition for a scaffold-ready workspace;
- legacy aliases for current draft and deterministic-init clients.

Request fields must be structured. LLM chat may help infer values, but backend
state must not depend on parsing a free-form prompt.

## Mobile UI Contract

New Project begins with a mode choice:

- **Scaffold** — technical foundation only;
- **Build product** — current product-oriented flow.

Scaffold UI must:

- keep the first interaction short;
- show recommended stack presets and a custom option;
- expose target choices independently in custom mode;
- show whether Cloudflare will write remote resources;
- explain that AWS Terraform is preparation only and will not be applied;
- display the explicit list of product work that will be skipped;
- render scaffold phase progress and recoverable blockers;
- end with links/actions for workspace, GitHub, Cloudflare preview, Workbench,
  and **Start product**;
- never label a scaffold as an app preview or installable app.

Existing Product Factory history must include creation mode and filter/label
scaffold jobs without losing old history.

## Persistence And Idempotency

Persist:

- scaffold draft and approved contract;
- manifest version and compatibility view;
- target/provider plans and versions;
- phase status and command evidence;
- generated file hashes;
- Git/GitHub identities;
- Cloudflare resource identities;
- AWS readiness mode and validation evidence;
- Workbench scope;
- scaffold result/context pack;
- relationship to later Domain Factory runs.

Reruns must create or verify resources using stable identities. They must not
duplicate GitHub repositories, Workers, routes, or commits. Generated-overwrite
phases may replace only declared generated files and must block on conflicting
user-owned changes.

## Security And Operational Governance

- Redact credentials, tokens, secrets, keystore values, account ids where
  sensitive, and Authorization headers from evidence.
- Validate every generated path under `PROJECTS_ROOT`.
- Do not run arbitrary commands supplied by manifest fields.
- Pin or constrain framework/tool dependencies and persist lockfiles.
- Verify generated workflows do not upload secrets or unsigned release
  artifacts.
- Treat GitHub/Cloudflare writes as authorized only after the scaffold contract
  preview states them explicitly.
- Never apply Terraform in this feature.
- Never delete remote resources during rollback automatically.
- Rollback should disable/repoint newly created resources only through a
  separate approved action; local generated files are recovered through git.
- Existing unrelated worktree changes in the Bridge or generated repository
  must be preserved.

## Migration And Rollout

Rollout order:

1. Add manifest v2, compatibility adapter, and provider registry behind a
   disabled feature flag.
2. Add scaffold mode using existing providers where possible, without changing
   the default product flow.
3. Add SvelteKit, real Go, and React Native/Expo providers.
4. Add framework-neutral Android artifacts and React Native Bridge adapter.
5. Enable scaffold mode for internal projects.
6. Validate the stack matrix and recovery behavior.
7. Make the new recommended preset visible by default.
8. Consider changing the default product stack only in a later explicit
   product decision.

Existing projects remain on manifest v1 compatibility behavior until they are
explicitly migrated. New scaffold projects use manifest v2 from the start.

## Non-Goals

- Do not migrate the Codex Mobile Bridge application itself from Flutter.
- Do not remove Flutter support.
- Do not share UI components between React Native and SvelteKit.
- Do not design or implement business UX during scaffold mode.
- Do not select product roles, entities, workflows, persistence, or visual
  identity during scaffold mode.
- Do not provision AWS resources or run Terraform apply.
- Do not publish an APK from scaffold mode by default.
- Do not treat Expo Web as the selected web product when SvelteKit is chosen.
- Do not claim Go support until Go files and conformance evidence exist.
- Do not claim selected FastAPI/Go preview readiness while a different Worker
  implementation serves the API.
- Do not replace the current product creation flow until compatibility and
  migration tests pass.

## Functional Requirements

- **FR-001**: Project Factory supports explicit `scaffold` and `product`
  creation modes.
- **FR-002**: Scaffold intake is minimal, structured, and excludes product/UX
  questions.
- **FR-003**: Manifest v2 models mobile, web, API, infrastructure, and artifacts
  independently with v1 read compatibility.
- **FR-004**: A provider registry plans, generates, validates, and reports each
  target through common contracts.
- **FR-005**: Scaffold produces a buildable neutral baseline and stops at
  `scaffold_ready` without starting product work.
- **FR-006**: GitHub, Workbench, SDD, CI, persistence, recovery, and context
  packs work for scaffold projects.
- **FR-007**: React Native/Expo is a real mobile provider with deterministic
  Android build capability.
- **FR-008**: SvelteKit is a real web provider with Cloudflare-compatible output.
- **FR-009**: FastAPI and Go are real API providers conforming to the same
  OpenAPI contract.
- **FR-010**: Cloudflare scaffold behavior is honest about web, API, D1, and
  product readiness.
- **FR-011**: AWS Terraform readiness generates and validates files without
  applying infrastructure.
- **FR-012**: Android release orchestration is framework-neutral and Bridge
  registration consumes normalized verified artifacts.
- **FR-013**: A user-triggered Start Product transition reuses the scaffold and
  activates Domain Factory.
- **FR-014**: Existing Flutter/Svelte manifest v1 projects remain readable,
  resumable, and unchanged unless explicitly migrated.
- **FR-015**: Security, real-data release policy, secret redaction, path safety,
  and remote-resource idempotency remain enforced.

## Acceptance Criteria

- **AC-001**: New Project options and UI expose Scaffold and Build Product with
  clear behavioral differences.
- **AC-002**: A default scaffold can be confirmed after project name, stack,
  Cloudflare, and AWS readiness decisions, with conditional GitHub/admin
  questions only when needed.
- **AC-003**: Scaffold intake does not request or infer business type, entities,
  roles, workflows, screens, navigation, brand, colors, or visual references.
- **AC-004**: Manifest v2 represents React Native mobile + SvelteKit web +
  FastAPI or Go API without encoding them as one frontend strategy.
- **AC-005**: Reading a v1 Flutter or Svelte project produces the documented
  compatibility view without rewriting files.
- **AC-006**: Provider capability results, not framework-name branches, decide
  phase execution and artifact promises.
- **AC-007**: React Native/Expo scaffold installs locked dependencies, typechecks,
  tests, prebuilds/builds Android in validation, and contains no product UX.
- **AC-008**: SvelteKit scaffold typechecks, tests, builds Cloudflare-compatible
  output, and contains only the neutral scaffold route.
- **AC-009**: Selecting Go generates Go source, module metadata, tests, binary
  build evidence, and OpenAPI conformance; no FastAPI files are generated.
- **AC-010**: FastAPI and Go pass the same black-box health/error/version
  conformance suite.
- **AC-011**: A scaffold job creates or verifies a clean local commit, GitHub
  repo/push when configured, Workbench discovery, and persisted result/context.
- **AC-012**: Cloudflare provision mode publishes a neutral operational preview
  that reports `api_ready=false`, `product_ready=false`, `d1=false`, and no
  installable claim.
- **AC-013**: Cloudflare generate-only and disabled modes perform no remote
  Cloudflare writes.
- **AC-014**: Terraform-ready mode generates formatted, validated, state-ignored
  files and never executes apply or creates AWS resources.
- **AC-015**: Scaffold completes as `scaffold_ready` without Domain Factory,
  UX lane, product generator/reviewer, APK release, or Bridge installable
  registration.
- **AC-016**: Missing remote credentials produce
  `scaffold_blocked_with_context` while preserving the valid local scaffold and
  exact recovery actions.
- **AC-017**: Start Product creates/activates a related Domain Factory run in the
  same workspace and does not recreate GitHub, Cloudflare, or Workbench
  identities.
- **AC-018**: Android release code can build/publish verified Flutter and React
  Native APKs through provider adapters and the same normalized Bridge
  registration contract.
- **AC-019**: A scaffold APK is not published or registered unless a separate
  explicit release action overrides the default after validation.
- **AC-020**: Product releases still fail on mock/local/placeholder API config,
  missing signing, package mismatch, invalid checksum, or missing release
  evidence.
- **AC-021**: History, restart recovery, and phase polling preserve creation
  mode and target/provider state.
- **AC-022**: Generated files, logs, context packs, workflows, Terraform, and
  manifests contain no secrets.
- **AC-023**: The documented compatibility matrix passes for Flutter legacy,
  React Native + SvelteKit + FastAPI, React Native + SvelteKit + Go, Flutter +
  SvelteKit + Go, and SvelteKit web-only.
- **AC-024**: Focused backend, Flutter UI, Node/SvelteKit/Expo, Go, Cloudflare,
  Terraform, SDD, Android release, and migration tests pass before rollout.

## Open Decisions With Recommended Defaults

These decisions are resolved by this spec unless implementation evidence forces
an explicit revision:

- React Native framework: Expo with pinned prebuild; EAS optional.
- Web framework: SvelteKit for new v2 projects.
- Recommended API default: FastAPI, with Go first-class and equivalent.
- Scaffold bootstrap: buildable, neutral technical shell.
- Cloudflare default: provision neutral web scaffold when credentials exist;
  D1 disabled.
- AWS default: none; `terraform_ready` is opt-in and never applied.
- Scaffold Android release: disabled.
- Domain Factory after scaffold: explicit Start Product only.
- Existing product default: unchanged until a later explicit rollout decision.
