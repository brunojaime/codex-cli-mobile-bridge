# Plan

This file is the root plan index. The initial implementation can use these
plans directly or split them into nested Workbench plan directories later.

## Plan 1: Domain Factory Contract And Baseline Context

Status: completed

Define the project-scoped Domain Factory contract, context payload, baseline
source discovery, and safety rules that prevent redoing deterministic init.

Tasks: T001-T006

## Plan 2: Mobile Entry Point And Chat Mode Activation

Status: completed

Fold Domain Factory into the New Project flow and configure the generated
project chat with project-scoped Domain Factory mode after deterministic init.

Tasks: T007-T012

## Plan 3: Domain Intake, References, And Role Model

Status: completed

Collect domain requirements, visual references, role/permission needs, entity
relationships, and release acceptance criteria without asking baseline setup
questions again.

Tasks: T013-T019

## Plan 4: Generator And Reviewer Domain Prompts

Status: completed

Create generator/reviewer prompts that consume baseline context, protect
foundation plumbing, prioritize visual/domain implementation, and require a new
preview release.

Tasks: T020-T024

## Plan 5: SDD And Workbench Integration

Status: completed

Persist Domain Factory intake into SDD, update spec/plan/tasks/traceability,
generate required diagrams, and make Workbench display the new domain work.

Tasks: T025-T030

## Plan 6: Domain Build Release Pipeline

Status: completed

After implementation starts, validate, build, publish, smoke, register, verify
updater behavior, and persist evidence for the next real preview APK/release.

Tasks: T031-T035

## Plan 7: Tests, Evidence, And Operational Guardrails

Status: completed

Add regression coverage, dry-runs, audit evidence, rollback guidance, and
guardrails for destructive operations.

Tasks: T036-T037
