---
id: 011-new-project-guided-intake
title: New Project Guided Intake
status: active
type: feature
domains:
  - project-factory
  - mobile
  - chat
  - sdd
  - generated-apps
related_specs:
  - 005-new-project-factory
  - 006-web-preview-delivery
  - 007-initial-preview-release
  - 009-sdd-status-normalization
  - 010-slash-command-palette
---

# New Project Guided Intake

## Intent

New Project must guide the user through a conversational contract before any
generator or reviewer work starts. The user should not need to know exact
phrases, field names, or implementation details. The system asks concrete
questions, suggests recommended answers, tracks assumptions, and builds only
after explicit structured confirmation.

## Product Outcome

When a user starts New Project:

- the existing New Project entry remains the primary entry point;
- an existing draft is reopened instead of duplicated;
- the agent explains that it is building a project contract;
- the system detects missing required information;
- the agent asks one or a small set of focused questions at a time;
- each question can show recommended options;
- selected options and free-text answers update the draft;
- defaults, assumptions, inferred values, and user-provided answers are
  traceable;
- the contract preview shows what will be generated, released, and blocked;
- generator/reviewer execution is impossible until the draft is confirmed.

## Core Rule

Project generation is gated by draft state, not by a loose natural-language
phrase. A confirmation message or command can only start the build when the
draft is already ready and the user has explicitly confirmed the contract.

## Relationship To Existing Factory

This spec does not replace the existing Project Factory. It adds a guided
intake layer above the current draft, asset, job, workflow, Workbench, release,
web preview, and installable-app systems.

Existing behavior must remain compatible:

- Project Factory options.
- Draft creation and persistence.
- Chat-first New Project mode.
- Attachment and Asset Depot flows.
- Reference assets.
- Generator/reviewer job runner.
- History and job recovery.
- Workbench and SDD generation.
- Runtime/release contracts.
- Web preview delivery.
- Android release and installable app registration.

## Draft State Machine

Drafts must expose a guided intake state:

- `collecting`: required information is missing.
- `ready_for_review`: enough information exists to show a contract preview.
- `changes_requested`: user asked to modify the preview.
- `confirmed`: user accepted the contract and build may be started.
- `build_started`: generator/reviewer job has started.
- `blocked`: intake cannot continue without external configuration or a
  non-recoverable validation issue.

Transitions:

- `collecting` -> `ready_for_review` when required questions are answered or
  safely defaulted.
- `ready_for_review` -> `changes_requested` when the user asks for changes.
- `changes_requested` -> `collecting` when new questions are needed.
- `ready_for_review` -> `confirmed` only by explicit structured confirmation.
- `confirmed` -> `build_started` only by a valid build action.
- any state -> `blocked` when a real blocker is detected.

## Question Model

Each guided question must be structured:

- `id`: stable machine id.
- `topic`: name, business, roles, assets, release, preview, or another domain.
- `question`: user-facing question.
- `why_it_matters`: short explanation.
- `options`: zero or more selectable answers.
- `recommended_option_id`: optional recommended answer.
- `free_text_allowed`: whether the user can answer freely.
- `required`: whether the contract is blocked without an answer.
- `answered`: whether the current draft has an answer.
- `answer`: normalized answer value when available.
- `answer_source`: `user`, `inferred`, `default`, `asset`, `prior_context`, or
  `system`.
- `confidence`: `low`, `medium`, or `high`.
- `affects`: fields or generation outputs affected by the answer.
- `depends_on`: optional prior question ids.
- `validation_error`: optional user-safe validation error.

Options must be structured:

- `id`
- `label`
- `description`
- `value`
- `recommended`
- `tradeoff`

## Required Intake Topics

The system must cover these topics before build readiness:

- project name and slug;
- business type;
- primary goal;
- target platforms;
- backend preference;
- expected users and roles;
- domain entities and admin-managed resources;
- admin emails for preview or release flows;
- visual direction;
- reference images;
- exact assets, logos, app icons, documents;
- runtime profile and initial release mode;
- GitHub publication expectations;
- Android APK/installable-app expectation;
- web preview expectation;
- Workbench/SDD expectations;
- external blockers such as missing credentials or unavailable release targets.

Not every topic requires a user question. Some can be inferred or defaulted, but
all must be visible in the contract preview with source and confidence.

## Recommended Options

The agent should propose options based on:

- user text;
- selected business type;
- attached assets and asset roles;
- visual references;
- existing Factory defaults;
- release profile contracts;
- previously answered questions;
- known blockers.

The recommended option must be marked clearly. The user can accept it, choose an
alternative, or answer freely when allowed.

## Contract Preview

When the draft reaches `ready_for_review`, the system must show a preview that
includes:

- project name, slug, business type, and primary goal;
- selected platforms and backend;
- roles and permissions baseline;
- domain entities and admin-managed resources;
- auth, Google placeholder, notifications, and updater assumptions;
- Workbench/SDD artifacts expected;
- web preview plan;
- Android/installable app plan;
- runtime profile/release profile plan;
- visual direction and asset usage;
- logo/app icon source decisions;
- defaults and assumptions;
- unresolved external blockers;
- risks and validation plan;
- what generator/reviewer will do next.

The preview must be persisted with the draft/job so history can explain why a
project was generated a certain way.

## Build Gate

Build can start only when:

- draft state is `confirmed`;
- all required questions are answered, defaulted, or explicitly waived;
- no blocking validation errors remain;
- assets referenced by the contract are still available;
- generator/reviewer settings are resolved;
- publication requirements are either configured or explicitly marked blocked;
- the user selected a structured build action.

If the user asks to build before readiness, the system must answer with the
smallest set of missing questions or blockers.

## Frontend Contract

The New Project UI remains chat-first:

- use existing New Project button entry;
- reopen active draft instead of creating duplicates;
- render current question cards inside the chat flow;
- show selectable recommended options;
- allow free-text answers;
- show answered/defaulted/inferred state;
- show contract preview;
- show confirm/build actions only when valid;
- show blocked state with clear next steps;
- keep existing asset role UI and chat attachments compatible.

If the slash command palette exists, this feature may contribute contextual
commands:

- project contract;
- project questions;
- project assets;
- project preview;
- project confirm;
- project build;
- project history;
- project cancel.

The guided intake must still work from the New Project button even if the slash
palette is not implemented yet.

## Backend Contract

The backend must persist guided intake data with the draft:

- current intake state;
- questions;
- answers;
- assumptions;
- missing required fields;
- contract preview;
- readiness summary;
- validation errors;
- created/updated timestamps.

Suggested endpoints or endpoint extensions:

- create/reopen guided draft;
- get draft intake state;
- answer question;
- update answer;
- list pending questions;
- generate contract preview;
- confirm contract;
- start build from confirmed draft.

Existing endpoints may be extended if that preserves compatibility.

## Safety Rules

- Never start generator/reviewer from `collecting`, `ready_for_review`, or
  `changes_requested`.
- Never treat a vague message as build confirmation if the draft is not ready.
- Never hide defaults that affect release, runtime profile, data mode, auth,
  roles, publication, or assets.
- Never lose asset role decisions during intake.
- Never duplicate drafts when the user reopens New Project.
- Never block local planning only because external credentials are missing;
  mark those as release blockers instead.

## Non-Goals

- Do not rewrite generated Flutter/FastAPI templates in this spec.
- Do not replace the generator/reviewer job runner.
- Do not change Android release policy.
- Do not change Web Preview provisioning.
- Do not remove the existing New Project button.
- Do not require slash command palette for the first guided intake slice.

## Acceptance Criteria

- Starting New Project enters guided intake instead of immediately building.
- A draft exposes required questions and missing fields.
- The UI can render a question with recommended options.
- Selecting an option updates the draft.
- Free-text answers are accepted where allowed.
- Contract preview includes decisions, defaults, assumptions, assets, and
  blockers.
- Build action is unavailable until the draft is confirmed.
- Confirmed draft can start the existing generator/reviewer workflow.
- Existing Project Factory endpoints remain backward compatible.
- Tests cover state transitions, question answer persistence, contract preview,
  blocked build attempts, and successful build start from confirmed state.
