# Tasks

## Plan 1: Creation Modes And Manifest V2

- [x] T001 Add `creation.mode` with `scaffold` and `product` values to Project Factory domain models, API schemas, persistence, and response payloads.
- [x] T002 Define manifest v2 schemas for project identity, mobile/web/API targets, infrastructure providers, artifacts, lifecycle state, and provider capability evidence.
- [x] T003 Define stack presets for React Native/Expo + SvelteKit + FastAPI, React Native/Expo + SvelteKit + Go, Flutter + SvelteKit + FastAPI/Go, and SvelteKit web-only.
- [x] T004 Define `bootstrap_level=buildable` and the neutral technical bootstrap rules, including forbidden product/domain/UX content.
- [x] T005 Define scaffold lifecycle states and allowed transitions from draft through `scaffold_ready` and later `domain_intake`.
- [x] T006 Implement a read-only manifest v1 compatibility adapter for Flutter, Svelte, FastAPI, Go declarations, legacy phase names, and missing creation mode.
- [x] T007 Ensure compatibility reads never rewrite existing manifests, drafts, jobs, generated files, or release history.
- [x] T008 Define capability calculation rules that distinguish declared, locally verified, remotely verified, prepared, blocked, skipped, and unsupported states.
- [x] T009 Add schema/serialization tests for v2 round trips, invalid combinations, legacy compatibility, and non-mutating reads.

## Plan 2: Provider Registry And Shared Contracts

- [x] T010 Define target kinds and provider protocol models for plan, scaffold, validate, doctor, runtime contract, release contract, evidence, artifacts, and blockers.
- [x] T011 Implement a provider registry with unique ids, target-kind validation, required tool declarations, capability declarations, and stable lookup errors.
- [x] T012 Register `flutter`, `react_native_expo`, and `none` mobile providers.
- [x] T013 Register `flutter_web`, `sveltekit`, and `none` web providers.
- [x] T014 Register `fastapi`, `go`, and `none` API providers.
- [x] T015 Register `cloudflare`, `terraform_ready`, `architecture_docs_only`, and `none` infrastructure/readiness providers in their correct target kinds.
- [x] T016 Define logical runtime configuration keys and provider mappings for Flutter dart-defines, Expo public config, SvelteKit public env, FastAPI env, and Go env.
- [x] T017 Replace new-code framework-name branches with provider capability queries while retaining legacy adapter paths for existing projects.
- [x] T018 Add registry, unknown-provider, capability-consistency, doctor, redaction, and provider-driven phase-selection tests.

## Plan 3: Scaffold API, Persistence, And Mobile Intake

- [x] T019 Extend Project Factory options with creation modes, target providers, stack presets, Cloudflare modes, AWS readiness modes, and recommended defaults.
- [x] T020 Add structured scaffold draft and contract-preview request/response models, including explicit remote effects and skipped product work.
- [x] T021 Add create/read/list/confirm scaffold draft endpoints or mode-aware extensions to existing Project Factory endpoints.
- [x] T022 Add start/resume/status/result endpoints for scaffold jobs with legacy deterministic-init aliases where required.
- [x] T023 Persist scaffold draft, approved contract, provider plans, job phases, relationships, resources, evidence hashes, result, and later Domain Factory relationship.
- [x] T024 Update New Project UI with the Scaffold and Build Product mode choice without changing the existing default product flow during the feature-flag stage.
- [x] T025 Build the short scaffold intake UI with recommended presets, custom independent targets, Cloudflare mode, AWS readiness, and conditional GitHub/admin questions.
- [x] T026 Show a confirmation preview that lists stack, remote writes, Terraform non-apply policy, no APK, no Domain Factory, and all intentionally skipped product/UX work.
- [x] T027 Render scaffold progress, blockers, recovery commands, creation-mode labels, workspace/GitHub/Cloudflare/Workbench links, and Start Product affordance.
- [x] T028 Add API, model, widget, persistence, restart-recovery, conditional-question, and old-client compatibility tests for scaffold intake and jobs.

## Plan 4: Deterministic Scaffold Runner And Shared Baseline

- [x] T029 Implement the scaffold phase state machine, ordering, idempotency rules, completion derivation, cancellation, retry, and blocked-with-context behavior.
- [x] T030 Implement `scaffold_preflight` for projects root, target conflicts, provider tools, GitHub, Cloudflare, Terraform, and Bridge configuration without remote writes.
- [x] T031 Implement `scaffold_contract` persistence with resolved slug, targets, capabilities, infrastructure modes, skipped product work, and content hash.
- [x] T032 Generate the shared scaffold repository shape: manifest, AGENTS, README, contracts, runtime schema, scripts, CI, release status, and infrastructure directories.
- [x] T033 Generate the infrastructure-only `000-project-scaffold` SDD package, indexes, diagrams metadata, technical decisions, pending product definition, and no inferred product content.
- [x] T034 Make Project Charter generation mode-aware so scaffold creates only technical identity/readiness content and does not invent objective, benefits, scope, brand, or client claims.
- [x] T035 Invoke selected target providers during `target_bootstrap` and preserve provider-specific evidence and generated file ownership.
- [x] T036 Implement `target_validation` with locked dependency installation, lint/analyze, typecheck, unit tests, builds, OpenAPI conformance, secret checks, and forbidden-product-content checks.
- [x] T037 Reuse/harden local git commit and GitHub create-or-verify/push behavior for scaffold jobs with clean-tree and idempotency evidence.
- [x] T038 Implement Workbench registration/discovery verification and write `.codex/factory/scaffold-result.json` plus `scaffold-context.md` with redacted structured state.
- [x] T039 Add runner tests for phase order, local-only success, remote blockers, retries, conflicting existing targets, generated-file ownership, clean commit, GitHub idempotency, and context attachment.

## Plan 5: React Native Expo And Framework-Neutral Android

- [x] T040 Implement the `react_native_expo` provider with pinned Expo/React Native/TypeScript dependencies and a reproducible lockfile.
- [x] T041 Generate a neutral Expo Router root/technical route with runtime/source-app diagnostics and no product route groups, navigation, auth, design, or mock data.
- [x] T042 Generate Expo app configuration, package id, version/build metadata, TypeScript config, lint/test/typecheck scripts, and secret-safe public runtime mapping.
- [x] T043 Implement deterministic Android native generation through pinned Expo prebuild/config plugins or an equivalent recorded process.
- [x] T044 Add React Native provider validation for dependency install, typecheck, lint, tests, Android prebuild/build, package metadata, no product UX, and no installable registration during scaffold.
- [x] T045 Create a reusable React Native Bridge package for source app identity and product-mode integration boundaries.
- [x] T046 Add product-mode React Native feedback support for screenshot/comment/bounds, optional audio, local queue, batch send, and release-when-complete parity.
- [x] T047 Add product-mode React Native Workbench launcher/deep-link behavior while keeping Workbench out of product navigation.
- [x] T048 Add product-mode React Native update checks, checksum/download handling, and Android installer handoff against the existing Bridge update contract.
- [x] T049 Define a framework-neutral Android build adapter interface for version/build resolution, command/env, output path, signing, metadata, tests, and artifact normalization.
- [x] T050 Refactor Android preview release and Bridge registration to consume the normalized Android artifact instead of Flutter pubspec/build assumptions.
- [x] T051 Add React Native scaffold, Bridge adapter, Android build/signing, GitHub prerelease, updater, installable registration, and Flutter regression tests.

## Plan 6: SvelteKit, FastAPI, Go, And OpenAPI Parity

- [x] T052 Implement the `sveltekit` provider with pinned TypeScript/SvelteKit dependencies, lockfile, and Cloudflare/static adapter selection.
- [x] T053 Generate only a neutral scaffold route, error route, runtime reader, source-app identity, and health/config diagnostics for SvelteKit scaffold mode.
- [x] T054 Add SvelteKit lint, typecheck, test, build, output validation, no-product-UX, and no-Android-claim tests.
- [x] T055 Define the scaffold OpenAPI contract for health, version metadata, correlation id, and normalized error payload.
- [x] T056 Generate/check TypeScript API client types used independently by React Native and SvelteKit without sharing UI components.
- [x] T057 Refactor the existing FastAPI generator into a real `fastapi` provider under `services/api` for manifest v2 projects.
- [x] T058 Limit FastAPI scaffold output to runtime config, health/version/error contract, tests, and container/build metadata; omit auth/RBAC/admin/domain features.
- [x] T059 Implement a real `go` provider with Go module metadata, source, config, health/version/error contract, tests, formatting, vet, and binary build.
- [x] T060 Ensure selecting Go emits no FastAPI project files or Python-only validation commands.
- [x] T061 Build a shared black-box OpenAPI conformance suite that runs against FastAPI and Go processes and verifies equivalent status, headers, and payload semantics.
- [x] T062 Persist API provider deployment status as prepared/deployed/blocked and prevent Cloudflare Worker/D1 from being mislabeled as FastAPI or Go.
- [x] T063 Add SvelteKit, FastAPI, Go, generated-client, OpenAPI drift, cross-provider parity, and current Svelte/Flutter compatibility tests.

## Plan 7: Cloudflare And AWS Terraform Readiness

- [x] T064 Define Cloudflare scaffold plan/result schemas for `provision_scaffold`, `generate_only`, and `disabled`.
- [x] T065 Generate a neutral infrastructure-owned scaffold page and health metadata when no SvelteKit/Flutter web target is selected.
- [x] T066 Generate provider-aware Cloudflare web build/deploy manifests that accept SvelteKit, Flutter Web, or neutral static output without coupling to mobile framework.
- [x] T067 Implement Cloudflare generate-only behavior with zero remote calls and explicit generated commands/configuration.
- [x] T068 Implement idempotent project-scoped Cloudflare scaffold provisioning, deploy, smoke, resource persistence, and recovery evidence.
- [x] T069 Enforce scaffold Cloudflare output `api_ready=false`, `product_ready=false`, `production_ready=false`, `d1=false`, and no installable claim unless separately verified later.
- [x] T070 Remove automatic D1 creation from scaffold mode and require an explicit post-scaffold persistence decision before provisioning it.
- [x] T071 Implement AWS `architecture_docs_only` output with undecided service choices and product-phase decision gates.
- [x] T072 Implement resource-neutral `terraform_ready` files with pinned versions/providers, environments, variables, tags, outputs, state bootstrap docs, ignores, format, and validate.
- [x] T073 Add Cloudflare no-write/provision/idempotency tests and Terraform tests proving no apply/resource creation, no state/secrets, correct formatting, and honest readiness.

## Plan 8: Scaffold Completion And Start Product Transition

- [x] T074 Derive `scaffold_ready` only when all requested local phases and authorized remote phases are completed or explicitly not requested.
- [x] T075 Derive `scaffold_blocked_with_context` when remote/configuration work is blocked while preserving the valid local project and exact next actions.
- [x] T076 Ensure scaffold completion skips Domain Factory, UX lane, product generator/reviewer, Android publication, Bridge installable registration, and product preview claims.
- [x] T077 Add workspace, GitHub, Cloudflare preview, Workbench, validation, pending API deployment, pending product, and AWS readiness fields to the scaffold result/context pack.
- [x] T078 Add an explicit Start Product API authorized only for a `scaffold_ready` workspace and current user action.
- [x] T079 Reuse repository, workspace, source app, target providers, GitHub remote, Cloudflare resources, Workbench scope, and scaffold context when starting Domain Factory.
- [x] T080 Update Domain Factory baseline context so it recognizes manifest v2 targets, scaffold state, intentionally absent product foundation, and pending deployment decisions.
- [x] T081 Update Domain Factory/UX prompts to own product navigation, design, auth, roles, persistence, feedback/updater wiring, and releases without rebuilding scaffold resources.
- [x] T082 Add transition tests for explicit authorization, same-workspace reuse, no duplicate resources, product intake activation, absent automatic activation, and relationship persistence.

## Plan 9: Compatibility Matrix, Security, And Rollout

- [x] T083 Add migration fixtures and regression tests for v1 Flutter, v1 Svelte, legacy Go declarations that generated FastAPI, interrupted init jobs, and old mobile API clients.
- [x] T084 Add end-to-end scaffold test for React Native/Expo + SvelteKit + FastAPI with local validation, Git/GitHub fakes, Cloudflare fake, Workbench, and context pack.
- [x] T085 Add end-to-end scaffold test for React Native/Expo + SvelteKit + Go.
- [x] T086 Add end-to-end scaffold test for Flutter + SvelteKit + Go.
- [x] T087 Add end-to-end scaffold test for SvelteKit web-only with no mobile/APK/installable phases.
- [x] T088 Add tests that reject product/domain/UX content, auth/RBAC/admin scaffolding, mock/demo data, APK publication, and D1 creation during default scaffold.
- [x] T089 Add secret redaction, path traversal, unsafe command, dependency pin/lock, generated-file ownership, workflow upload, and unrelated-worktree preservation tests.
- [x] T090 Add product release regression tests for real preview URLs, runtime profiles, signing, package id, checksum, tag patterns, updater metadata, and Bridge registration for Flutter and React Native.
- [x] T091 Add feature flags and staged rollout configuration that preserve the existing Product default until compatibility evidence is approved.
- [x] T092 Document operator workflows for scaffold creation, blocked recovery, opening Workbench, choosing Start Product, Terraform review, and optional later release.
- [x] T093 Document manifest v1 compatibility, explicit migration procedure, provider authoring, stack presets, and rollback boundaries.
- [x] T094 Run and record focused backend, Flutter, Node/Expo/SvelteKit, Go, Cloudflare, Terraform, SDD doctor, Android release, security, and end-to-end validation before enabling rollout.

### T094 Independent audit evidence — 2026-08-08

- Clean temporary workspaces validated Expo/SvelteKit/FastAPI/Terraform,
  SvelteKit/Go, and Flutter mobile/web, including real Android and web builds,
  clean Git status, and Cloudflare `--dry-run` asset resolution.
- The shared FastAPI/Go black-box suite ran with Go 1.24.0 present and skipped
  neither provider.
- Negative coverage now includes feature-gate bypass, blocked Start Product,
  direct Domain Factory bypass, unsafe provider argv, workspace symlinks/path
  traversal, generated-file conflicts, wrong GitHub origin, protected-preview
  public fallback, Android signature/package/checksum failures, cancellation
  persistence/retry, and exact post-commit infrastructure ownership.
- Repository hygiene checks found no tracked APK/AAB, keystore, Terraform state,
  `.terraform`, `node_modules`, `.svelte-kit`, `.venv`, or build output. Existing
  ignored local release/signing files were preserved and were not introduced by
  Scaffold validation.
