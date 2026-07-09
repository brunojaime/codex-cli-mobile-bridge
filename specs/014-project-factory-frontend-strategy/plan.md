# Project Factory Frontend Strategy Plan

## Phase 1: Strategy Domain Contract

Define the frontend strategy registry, strategy capability schema, strategy
selection rules, and release capability semantics for Flutter and Svelte.

## Phase 2: Project Factory Intake And Manifest

Expose `frontendStrategy` in backend options, API schemas, mobile UI request
payloads, draft/job summaries, and manifest planning.

## Phase 3: Flutter Strategy Hardening

Extract current Flutter assumptions into an explicit Flutter strategy and verify
that Android preview APK, Workbench, Bridge installable registration, and
Cloudflare preview still pass unchanged.

## Phase 4: Svelte Web Strategy Generation

Generate an independent Svelte web app, strategy config, tests, build scripts,
and Cloudflare web preview assets without claiming Android installability.

## Phase 5: Shared Cloudflare Preview Runtime

Make the Cloudflare Worker/D1 preview backend reusable across strategies while
keeping strategy-specific web asset build and validation paths.

## Phase 6: Strategy-Aware Release Orchestration

Make publication phases, release output, Bridge registration, blockers, and
readiness checks depend on declared strategy capabilities.

## Phase 7: Validation Matrix And Rollout

Add contract tests, generated project tests, Flutter tests, Svelte tests, worker
tests, and regression coverage for unsupported strategy combinations.
