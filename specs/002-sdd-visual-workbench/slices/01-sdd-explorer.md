# Slice 1: SDD Explorer

## Goal

Provide a read-only explorer for the current project's SDD artifacts.

## User Experience

The user opens the dev workbench and sees:

- Project name and workspace path.
- Contract status from the SDD snapshot.
- Constitution.
- Specs list.
- Plan and tasks for each spec.
- Diagram source files.

## Backend Dependency

- `GET /sdd/projects`
- `GET /sdd/project?workspace_path=...`
- `GET /sdd/project/diagrams?workspace_path=...`

## Done When

- The explorer loads real backend SDD data.
- The explorer uses the existing read-only SDD endpoints.
- Missing or oversized files are visible.
- No mock data, seeded state, placeholder API URL, or fake workspace is used.
- The normal app is unchanged when dev mode is off.
