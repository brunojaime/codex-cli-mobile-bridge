# Plan

This file is the plan index for the Project Charter Documentation Framework.
Task numbering is local to this spec and mirrored in `tasks.md` and
`tree.json`.

## Plan 1: Charter Contract And Data Model

- Status: `completed`
- Goal: Define the project-management document contract, metadata schema,
  versioning state model, validation result shape, and manifest integration.
- Tasks: `7`

## Plan 2: Deterministic Project Factory Baseline

- Status: `completed`
- Goal: Generate the documentation framework and initial charter during New
  Project creation using the approved draft/contract instead of generic
  metadata.
- Tasks: `8`

## Plan 3: Modular Context And Natural-Language Routing

- Status: `completed`
- Goal: Let agents update charter content from natural language while loading
  only the relevant documentation module.
- Tasks: `7`

## Plan 4: Versioning, Changelog, Validation, And Release Snapshots

- Status: `completed`
- Goal: Separate draft work from client-delivered versions, enforce immutable
  releases, and block invalid export.
- Tasks: `8`

## Plan 5: Rendering And Export Pipeline

- Status: `completed`
- Goal: Render Markdown source into a PDF-like document view and prepare later
  PDF export without making PDF the source of truth.
- Tasks: `7`

## Plan 6: Backend Document APIs And Workbench Indexing

- Status: `completed`
- Goal: Expose project documents through safe backend APIs and Workbench/SDD
  discovery without treating the charter as a feature spec.
- Tasks: `7`

## Plan 7: Flutter/Workbench Viewer

- Status: `completed`
- Goal: Add a mobile/workbench document surface that shows the latest rendered
  charter with status, validation, and optional version history.
- Tasks: `8`

## Plan 8: Validation, Migration, And Documentation

- Status: `completed`
- Goal: Add regression tests, migrate generated-project assumptions, document
  operator usage, and keep current behavior compatible.
- Tasks: `6`

## Plan 9: Agent Lifecycle And Complete Email Sharing

- Status: `completed`
- Goal: Make the Acta required evolving context for all Project Factory agent
  stages, keep delivery explicit, and expose comfortable mobile reading plus
  complete multi-recipient email sharing from the SDD document surface.
- Tasks: `6`
