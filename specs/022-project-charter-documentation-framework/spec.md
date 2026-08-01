---
id: 022-project-charter-documentation-framework
title: Project Charter Documentation Framework
status: completed
type: feature
domains:
  - project-factory
  - project-management
  - workbench
  - sdd
  - mobile
  - document-rendering
related_specs:
  - 005-new-project-factory
  - 011-new-project-guided-intake
  - 017-new-project-deterministic-init-pipeline
  - 019-domain-factory-mode
  - 021-ux-agent-lane
---

# Project Charter Documentation Framework

## Intent

Every new project created by Codex Mobile Bridge must start with a first-class
Project Charter ("Acta de Proyecto") documentation framework. The charter is a
client-facing deliverable and a working context for agents. It explains why the
project exists, what product outcome is expected, which benefits matter, and
which information is still pending.

The charter must be created during New Project deterministic initialization,
must be visible from the mobile/workbench UI, and must be safe to evolve through
natural-language requests such as "agreguemos beneficios al acta", "armemos la
WBS", or "actualiza el objetivo del producto". Agents must understand the
document model without loading unrelated matrices, WBS, roles, or risk context
until those modules are requested.

## Product Outcome

When a user creates a New Project:

- the generated project includes a Project Charter workspace from the first
  baseline commit;
- the initial charter is clean, minimal, and client-deliverable after review;
- the initial charter includes project identity, logo decision, revision
  history, index, executive summary, project objective, product objective,
  expected benefits, preliminary scope, and pending definitions;
- the charter is rendered in the mobile/workbench app in a PDF-like layout so
  the user can see how the client-facing document will look;
- the latest rendered charter is easy to open from the SDD/Workbench area;
- previous delivered versions are stored, but the latest version is the primary
  UI surface;
- natural-language requests can update the charter or a specific charter
  module;
- agents can detect that a change belongs in the charter and update it when the
  user's request implies charter impact;
- delivered versions are immutable snapshots;
- client-visible version numbers increase only when a delivered version changes
  and is delivered again;
- draft/internal edits do not force a client version bump;
- deterministic validation blocks client export when required fields, logo
  decisions, revision history, or changelog rules are missing.

## Non-Goals

- Do not build a full collaborative document editor in the first delivery.
- Do not require DOCX editing as the source of truth.
- Do not force the user to manually edit Markdown.
- Do not load WBS, roles, risks, or alternatives context when only the charter
  introduction is being edited.
- Do not expose all historical versions as the primary UI; latest version is the
  default view.
- Do not allow generated placeholders such as TODO/lorem ipsum in a delivered
  client export.
- Do not create mock/demo project data as part of this documentation feature.

## Core Concepts

### Project Charter

The Project Charter is the first client-facing project document. It defines:

- project identity;
- why the project exists;
- the project objective, meaning the temporary work to be executed;
- the product objective, meaning the durable product capability to be delivered;
- expected business benefits;
- preliminary scope;
- pending definitions;
- revision and delivery state.

### Documentation Framework

The framework is bigger than the first charter page. It includes modular
documentation areas for future project-management deliverables:

- charter;
- WBS/EDT;
- roles and responsibilities;
- skills and competencies;
- risks;
- decision/alternative matrices;
- delivery/version history.

Only the relevant module should be loaded for agent work.

### Delivered Version

A delivered version is a snapshot sent or intended to be sent to the client. It
has a stable version, timestamp, rendered artifact, source hash, revision log,
and immutable release directory.

### Draft Version

A draft is active working content. Draft edits can happen freely without
changing the latest client-visible version.

## Generated Project Shape

New Project generation must add this structure:

```text
docs/project-management/
  index.md
  glossary.md
  versioning.md
  context-routing.md

  acta/
    README.md
    current/
      acta.md
      metadata.yaml
      brand.yaml
      render.html
      render-manifest.json
    releases/
      .gitkeep
    changelog.md
    validation-rules.md
    export-rules.md

  wbs/
    README.md
    wbs.md
    wbs.puml

  roles/
    README.md
    roles-responsibilities.md
    skills-competencies.md

  risks/
    README.md
    risks.md

  alternatives/
    README.md
    decision-matrix-template.md

assets/brand/
  .gitkeep
```

The generated `.codex/project.yaml` must reference the documentation framework:

```yaml
project_management:
  enabled: true
  standard: project-charter/v1
  primary_document: docs/project-management/acta/current/acta.md
  latest_render: docs/project-management/acta/current/render.html
  latest_release: null
  modules:
    charter: docs/project-management/acta/README.md
    wbs: docs/project-management/wbs/README.md
    roles: docs/project-management/roles/README.md
    risks: docs/project-management/risks/README.md
    alternatives: docs/project-management/alternatives/README.md
```

## Initial Charter Content

The generated first charter must include:

1. Cover:
   - project name;
   - client/organization;
   - project logo or logo decision;
   - document title;
   - version;
   - date;
   - author/responsible role;
   - status.
2. Revision history:
   - date;
   - version;
   - status;
   - description;
   - author;
   - delivered flag.
3. Index.
4. Executive summary.
5. Project objective.
6. Product objective.
7. Expected benefits.
8. Preliminary scope:
   - included;
   - not included, if known.
9. Pending definitions.

The first generated charter may use inferred content from the New Project
contract, but every inferred field must be marked in metadata with source and
confidence. Unknown information must be represented as pending definitions, not
as fake content.

## Logo And Brand Rules

The charter must include an explicit logo decision:

- `provided`: user supplied a logo or exact brand asset;
- `generated`: system generated a project mark;
- `pending`: no logo exists yet;
- `not_required`: client-facing output does not require a logo.

The `brand.yaml` file must track:

```yaml
logo_status: provided | generated | pending | not_required
logo_source: user_upload | generated | none
client_pdf_requires_logo: true
logo_path: assets/brand/logo.png
notes: ""
```

Client export is blocked when `client_pdf_requires_logo: true` and
`logo_status: pending`.

## Versioning Rules

Document states:

- `draft`;
- `internal_review`;
- `client_delivered`;
- `client_revised`;
- `superseded`.

Version rules:

- `v0.x` is internal draft work.
- `v1.0` is the first client-delivered version.
- `v1.x` is a minor client-delivered update.
- `v2.0` is a structural update, such as changed project objective, product
  objective, major scope, or major benefits.
- Draft edits do not bump the latest client-visible version.
- A delivered version must be snapshotted under
  `docs/project-management/acta/releases/vX.Y/`.
- Delivered snapshots are immutable. New changes create a new version.
- If a delivered charter changes in objective, product objective, benefits,
  scope, or pending definitions, a changelog entry is required.

Each release directory must include:

```text
acta.md
render.html
acta.pdf        # optional in the first delivery, required when PDF export exists
metadata.yaml
source-hash.txt
```

## Natural Language Contract

Users can request charter work in natural language. Examples:

- "agrega estos beneficios al acta";
- "actualiza el objetivo del producto";
- "esto deberia ir en el acta";
- "armemos la WBS";
- "pasalo a una version para entregar";
- "quiero ver como queda el documento";
- "exporta la ultima acta para el cliente".

Agents must classify the request:

- charter identity/metadata;
- executive summary;
- project objective;
- product objective;
- benefits;
- scope;
- pending definitions;
- versioning/release;
- render/export;
- WBS module;
- roles module;
- risks module;
- alternatives module.

When the request is charter-only, agents should read:

- `docs/project-management/index.md`;
- `docs/project-management/acta/README.md`;
- `docs/project-management/acta/current/acta.md`;
- `docs/project-management/acta/current/metadata.yaml`;
- `docs/project-management/acta/validation-rules.md`.

Agents must not read WBS, roles, risks, or alternatives modules unless the
request asks for those modules or the charter explicitly references them as
needed.

## Agent Behavior Rules

Agents may update the charter when:

- the user explicitly asks to update the acta/project charter;
- the user asks for content that clearly belongs in the charter;
- the user asks to prepare a client-facing project document;
- the user approves moving a draft to a delivered version;
- a New Project contract changes a field that the charter mirrors.

Agents must not silently deliver a version. Delivery/export requires explicit
user intent such as "entregar", "exportar", "mandar al cliente", "versionar",
or a structured UI action.

When a delivered version exists and a charter-impacting change is requested,
the agent must:

- edit the draft/current charter;
- keep the current client-visible version unchanged;
- add a pending changelog entry or delivery note;
- explain that the next client export will require a version bump.

## Rendering And Export

Markdown remains the source of truth for the first delivery. The system renders
the charter to a PDF-like document view.

Preferred first delivery:

- render Markdown to sanitized HTML with print CSS;
- show the HTML in Flutter using an embedded viewer/WebView or equivalent;
- use the same CSS for client export;
- add PDF export later using a deterministic renderer such as Chromium/Pandoc
  when available.

The UI must make the latest charter easy to inspect. The view should look like
the client document, not like raw Markdown.

## Workbench And Mobile UI Contract

The SDD/Workbench area must expose a new document surface:

- a "Documents" or "Project Charter" section;
- latest charter preview by default;
- document status, version, and last update;
- visible validation state;
- optional previous versions panel;
- action to request natural-language changes in chat;
- action to render/refresh preview;
- action to mark/export a client version when validation passes.

Editing in the first delivery may be natural-language driven instead of direct
rich-text editing. Direct editing can be deferred.

## Backend API Contract

Suggested backend endpoints:

- `GET /project-documents?workspace_path=...`
- `GET /project-documents/charter?workspace_path=...`
- `GET /project-documents/charter/render?workspace_path=...`
- `POST /project-documents/charter/validate`
- `POST /project-documents/charter/render`
- `POST /project-documents/charter/release`
- `GET /project-documents/charter/releases`
- `GET /project-documents/charter/releases/{version}`

The API can be backed by filesystem documents in generated projects. It must
validate paths under the workspace and must not write outside the project root.

## Deterministic Validation

Validation must block client release/export when:

- project name is missing;
- client/organization is missing or explicitly required and unknown;
- version is missing;
- status is invalid;
- revision history is missing;
- project objective is missing;
- product objective is missing;
- benefits are missing;
- logo decision is missing;
- required logo is pending;
- source contains TODO/lorem ipsum/client-visible placeholders;
- delivered version would overwrite an existing immutable release;
- changelog is missing when a prior delivered version exists and content changed;
- render output is stale compared with source hash.

## Relationship To SDD

The Project Charter is not a replacement for SDD specs. It is a project
management/documentation artifact.

The Workbench should index it as a document/project-management surface. It may
appear near SDD because the same app area is used for project understanding,
but it should not be treated as a feature spec unless a later SDD extension
defines a formal `project-management` artifact type.

## Acceptance Criteria

- AC-001: A new project generated by Project Factory includes the project
  management documentation structure and an initial charter.
- AC-002: The deterministic init pipeline uses the approved draft/contract data
  when generating charter content and does not rebuild generic project metadata.
- AC-003: The generated charter has the required initial sections and explicit
  pending definitions for unknown data.
- AC-004: The generated project records logo decision metadata and blocks
  client export when a required logo is pending.
- AC-005: Agents have module-specific README/context routing so charter-only
  work does not load WBS, roles, risks, or alternatives context.
- AC-006: Natural-language charter requests can be classified and routed to the
  correct document module.
- AC-007: Draft edits do not bump the latest client-visible version.
- AC-008: Client delivery snapshots are immutable and include source hash,
  metadata, rendered artifact, and changelog linkage.
- AC-009: Validation blocks export/release when required fields, logo decision,
  revision history, stale render, or placeholders are present.
- AC-010: The mobile/workbench UI exposes a Project Charter/Documents section
  that shows the latest rendered charter in a PDF-like layout.
- AC-011: The latest charter view shows version, status, validation state, and
  last rendered timestamp.
- AC-012: Previous versions are accessible but secondary to the latest view.
- AC-013: Tests cover generator output, deterministic init, validation,
  versioning, natural-language routing, backend APIs, and Flutter UI rendering.
