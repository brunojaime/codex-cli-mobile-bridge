# Operator Workflow

This workflow describes how operators should use the Project Charter framework
after it is generated with a new project.

## 1. Create Project

1. Start New Project from the Workbench/chat UI.
2. Complete or confirm the guided intake contract.
3. Include project name, project objective, product objective, expected
   benefits, preliminary scope, initial admin emails, logo mode, and any
   visual references that are already known.
4. Approve generation only after the contract is ready.

Project Factory creates the software baseline and the documentation framework
together. The initial charter is a draft and is not a client-delivered version.

## 2. Review Current Charter

Open `Documents` from the active project chat/workbench session. Review:

- charter status and draft version
- latest delivered version, if any
- updated timestamp
- validation state and blocking issues
- render freshness
- module context list
- latest HTML preview

The Flutter viewer uses the sanitized rendered HTML as a safe preview source.
Markdown remains the source of truth.

## 3. Request Natural-Language Changes

Use the `Request charter change` action or the chat composer. Examples:

- `agreguemos beneficios al acta`
- `cambiemos el objetivo del producto`
- `sumemos una definicion pendiente del alcance`

Agents should load only the charter context unless the request explicitly names
another module such as WBS, roles, risks, or alternatives.

Changing draft content updates hashes and timestamps but does not bump the
latest delivered version.

## 4. Refresh Render

After charter source changes:

1. Use `Refresh render`.
2. Confirm the render state is fresh.
3. Review the preview again.

Client export must be blocked when the render is stale relative to `acta.md`.

## 5. Validate

Run validation before delivery. Blocking issues include:

- missing required files or metadata
- invalid document status
- missing revision history
- pending required logo decision
- TODO/lorem ipsum/generic placeholders in client-deliverable sections
- stale source/render hashes

If a logo is required for client PDF/export and `brand.yaml` has a pending logo
status, delivery must remain blocked until the logo is provided, generated, or
explicitly waived.

## 6. Deliver Client Version

Create a client-delivered version only when the user explicitly asks to prepare,
deliver, release, or export a client version.

Delivery rules:

- first delivered version is normally `v1.0`
- draft edits stay on `v0.x`
- minor delivered changes use `v1.x`
- major charter changes such as product objective or preliminary scope changes
  require a major version recommendation
- existing release directories are immutable and must not be overwritten
- after a prior delivered release, charter-impacting changes need a changelog
  entry before release

The release snapshot is written under:

```text
docs/project-management/acta/releases/vX.Y/
```

## 7. Expand Other Modules Later

The initial acta workflow should not load WBS, roles, risks, or alternatives by
default. Expand those modules only when the operator asks for them:

- WBS: when planning decomposition or delivery structure
- roles: when defining responsibilities and accountability
- risks: when identifying risk register or mitigations
- alternatives: when comparing tool, infrastructure, broker, or device options

Each module has its own README and context rules so the agent can work without
loading unrelated documentation.
