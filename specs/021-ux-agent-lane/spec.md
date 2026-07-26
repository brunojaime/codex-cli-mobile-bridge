# UX Agent Lane

id: 021-ux-agent-lane
status: mvp-slice
owner: codex-mobile-bridge

## Intent

Add a UX lane to New Project and manual project improvement runs. The target
architecture is a first-class lane with two dedicated agents:

- `ux_generator`: a Senior UX implementation agent that changes the product UI,
  visible copy, layout, interaction states, visual hierarchy, accessibility, and
  validation evidence.
- `ux_reviewer`: a UX reviewer that independently reviews the UX generator's
  diff, screenshots, benchmark notes, UAT scenarios, accessibility checks, and
  remaining visual risk.

This replaces the current single advisory `ux` specialist for project creation
and Domain Factory work. The existing `ux` supervisor member may remain for
generic advisory use, but the new lane is the default for serious product UX
improvement because it can act, validate, and require another UX pass.

## Implemented Scope

The implementation is still label-based for compatibility with existing chat
agent ids, but the product workflow is first-class and visible. The existing
`generator`/`reviewer` ids can be labeled as `UX Generator`, `UX Reviewer`,
`Domain Generator`, and `Domain Reviewer` depending on the stage.

Implemented now:

- manual `/ux` configures the existing `generator` agent as `UX Generator`;
- manual `/ux-full` configures the existing `generator` and `reviewer` agents
  as `UX Generator` and `UX Reviewer` with a 15-turn budget;
- `/ux-full` is blocked unless the selected chat has a workspace;
- Project Factory runner fails closed before UX phases when the
  `visual-ux-polish` skill and required reference files cannot be loaded;
- Project Factory runner adds a pre-planning UX brief step and requires
  `.codex/ux/pre-project-ux-brief.md` before downstream planning/generation;
- downstream planning, generator, reviewer, and UX prompts explicitly require
  reading `.codex/ux/pre-project-ux-brief.md`;
- Project Factory runner adds a post-factory `ux_generator -> ux_reviewer`
  loop with a maximum of 10 passes and reviewer-controlled early stop;
- Project Factory runner writes `.codex/ux/evidence-index.json` listing UX
  artifacts produced under `.codex/ux/`.
- Domain Factory state, intake contracts, prompts, and workflow evidence expose
  the agreed domain UX sequence:
  `ux_generator -> ux_reviewer -> ux_generator -> domain_generator ->
  domain_reviewer -> ux_generator -> ux_reviewer`.
- Project Factory runner executes the early UX baseline as
  `UX Generator -> UX Reviewer -> UX Generator` before downstream planning and
  generator/reviewer implementation prompts consume the UX brief.
- Project Factory init exposes the automatic UX baseline as visible chat
  messages. Each UX pass first appears as a pending/running message and is then
  updated with a short completion/failure summary and evidence path.
- Domain Factory labels the paired functional implementation agents as
  `Domain Generator` and `Domain Reviewer` so their chat turns are distinct
  from the overall Domain Factory phase.

Deferred:

- first-class `ux_generator`/`ux_reviewer` ids, API schema fields, lifecycle
  states;
- backend Project Factory reviewer JSON parsing/continue routing for multiple
  automatic UX iterations;
- attached UX evidence in session projections or Workbench UI;
- release gates that fail on unresolved UX findings.

## Product Outcome

For every new generated project, the user gets a professional first experience
instead of a raw functional baseline:

- the approved project contract includes a lightweight UX brief before Project
  Factory generates the baseline;
- baseline screens receive a strong UX generator/reviewer pass after Project
  Factory finishes;
- Domain Factory receives UX direction from the user's first domain brief before
  the paired domain generator/reviewer implementation starts;
- the paired Domain Factory generator/reviewer workflow is the functional
  implementation loop; there is no separate extra functional generator stage;
- after Domain Factory implementation, UX generator/reviewer can polish the real
  app visually while preserving domain behavior and release/runtime contracts;
- release readiness includes UX evidence, not only tests and backend smoke;
- benchmark findings, screenshots, and UX reviewer feedback are visible to both
  UX agents and preserved as run evidence;
- UX agents can improve the interface without changing domain behavior or
  backend contracts.

## Clean Product Baseline Contract

The deterministic Flutter/Svelte baseline is infrastructure, not product
information architecture. It must provide auth, preview runtime wiring, real
backend configuration, updater/feedback/workbench contracts, release scripts,
and validation hooks, but it must not impose visible product screens or
navigation destinations.

Generated Flutter apps must not ship with fixed product tabs or scaffold-owned
business screens unless the approved domain brief and UX lane explicitly select
equivalent domain-specific surfaces. Admin, notification, RBAC, persistence,
and invite APIs may remain available as implementation contracts for Domain
Factory, but the initial visible app shell must stay neutral until UX/Domain
work defines the actual product experience.

The UX Generator and UX Reviewer own these product decisions:

- information architecture and navigation model;
- primary screens and first-use flow;
- visual hierarchy, density, typography, colors, and interaction states;
- logo treatment and app icon source;
- empty, loading, error, invite, and authenticated states;
- accessibility and responsive fit.

If the user supplied a logo, app icon, or exact visual asset, the UX lane must
preserve and apply it. If no identity asset was supplied, the UX lane must
create a minimal domain-appropriate identity and app icon direction. If colors
or style are not specified, the UX lane chooses a professional direction that is
representative of the application category and records the rationale in
`.codex/ux/` evidence.

UX agents should reason from comparable professional products and current
platform best practices when the domain does not provide enough visual
direction. Benchmark notes and long evidence belong in `.codex/ux/`, while chat
messages should stay concise and conversational.

## Final Flow Decision

New Project and Domain Factory are one visible product-building workflow. The
deterministic phases remain the source of truth for infrastructure and release,
but every model-driven product pass must appear as an agent chat turn with a
short user-readable summary and an evidence path.

1. New Project intake creates the draft and asks only for missing setup data.
   If project name or admin emails were already captured in the New Project
   dialog, the chat must not ask for them again.
2. Deterministic init creates/verifies the baseline scaffold and frontend
   strategy. UX stays visible as `queued_waiting_for_domain_brief` until the
   user has provided the first business/domain brief.
3. The user sends the first domain brief and approves it with
   `PROJECT_FACTORY_READY_FOR_BUILD`. That marker is consumed by the backend;
   it must not create files, repositories, previews, APKs, or another project
   through normal chat generation.
4. Early UX baseline runs visibly in chat:
   `UX Generator -> UX Reviewer -> UX Generator`. It sets the visual direction,
   logo/icon plan, app name presentation, navigation, density, first screens,
   empty states, accessibility goals, and UX acceptance criteria before domain
   implementation starts.
5. Domain implementation runs visibly in chat:
   `Domain Generator -> Domain Reviewer`. This is the functional implementation
   loop. There is no additional functional Generator stage beyond this
   Domain Factory pair.
6. Final UX polish runs visibly in chat:
   `UX Generator <-> UX Reviewer` up to 10 iterations. The reviewer may stop
   early when the visual result is good enough. This stage may change UI code,
   copy, layout, responsiveness, interaction states, logos/icons, and UX
   evidence, while preserving domain behavior and release/runtime contracts.
7. Deterministic validation and release complete the flow: local validation,
   git commit, GitHub repository/tag/release, Cloudflare preview provision and
   deploy, preview smoke and initial admin invite, Android preview APK release,
   Bridge installable registration, Workbench/feedback verification, updater
   configuration, and LLM context pack.
8. When release is ready, the preview invite email is sent through the
   configured email provider using the configured sender. If no provider is
   available, the status must say manual delivery is required.

The Domain Factory automatic sequence after the first domain brief is:

```text
Project Factory contract and user domain brief
-> UX Generator
-> UX Reviewer
-> UX Generator
-> Domain Generator
-> Domain Reviewer
-> UX Generator <-> UX Reviewer, up to 10 passes
-> validation / preview / APK / Bridge
```

The first UX sequence is a direction-setting baseline. It reads the user's
domain brief and defines look and feel, visual tone, navigation expectations,
component direction, density, empty states, and accessibility criteria before
domain implementation starts. It does not introduce another functional
implementation agent.

The Domain Factory implementation stage is the existing paired
`domain_generator -> domain_reviewer` workflow. That pair owns both domain
modeling and functional implementation.

The final UX sequence runs after the app exists. It may change visible UI code,
copy, layout, responsive behavior, interaction states, and UX evidence, but must
preserve backend behavior, auth, RBAC, persistence, release wiring, updater
configuration, and real preview runtime paths. The reviewer may stop before the
10-pass limit when the visual result is good enough.

Chat output must be concise. Full prompt text, long model output, screenshots,
benchmark details, and reports are stored under `.codex/ux/` and referenced from
the visible chat message instead of being pasted into chat.

Long-running or manual UX work outside this automatic sequence remains
available through `/ux` and `/ux-full`.

## Research Basis

The lane is grounded in the local `visual-ux-polish` skill and these external
research/design references:

- Nielsen Norman Group defines usability testing as task-based observation to
  find design problems, opportunities, and user behavior/preferences:
  https://www.nngroup.com/articles/usability-testing-101/
- Nielsen Norman Group recommends competitive usability evaluation to compare
  how competing products solve the same design problems:
  https://www.nngroup.com/articles/competitive-usability-evaluations/
- Nielsen Norman Group frames UX methods across behavioral vs. attitudinal,
  qualitative vs. quantitative, and context-of-use dimensions:
  https://www.nngroup.com/articles/which-ux-research-methods/
- Nielsen Norman Group describes heuristic evaluation as a systematic expert
  review against usability guidelines:
  https://www.nngroup.com/articles/how-to-conduct-a-heuristic-evaluation/
- Nielsen Norman Group uses the 5-second test to gauge first impressions:
  https://www.nngroup.com/videos/5-second-usability-test/
- Nielsen Norman Group recommends task success, time on task, and satisfaction
  as core UX benchmark metrics:
  https://www.nngroup.com/articles/product-ux-benchmarks/
- Nielsen Norman Group treats success rate as a simple bottom-line usability
  metric:
  https://www.nngroup.com/articles/success-rate-the-simplest-usability-metric/
- W3C WCAG 2.2 is the accessibility baseline for contrast, reflow, focus, target
  size, keyboard access, and focus-not-obscured behavior:
  https://www.w3.org/WAI/WCAG22/quickref/
- Material Design 3 breakpoints and adaptive layout guidance calibrate Android
  and web responsive behavior:
  https://m3.material.io/foundations/layout/breakpoints/overview
- Apple Human Interface Guidelines calibrate iOS layout, legibility, touch
  target expectations, and platform fit:
  https://developer.apple.com/design/human-interface-guidelines/layout
- Apple first-launch guidance calibrates launch and first-screen readiness:
  https://developer.apple.com/design/human-interface-guidelines/launching
- UAT planning should derive scenarios from requirements and include expected
  results, realistic data, environment, and documented findings:
  https://www.splunk.com/en_us/blog/learn/user-acceptance-testing-uat.html
- Acceptance criteria must define the conditions a task or feature must meet to
  be accepted:
  https://www.atlassian.com/work-management/project-management/acceptance-criteria

These sources are inputs to the lane contract. Agents must not copy competitor
brands, proprietary assets, or distinctive layouts.

## Required Skill Execution Contract

`visual-ux-polish` must be a required execution input, not just a line in the
agent prompt. The backend runner must resolve the skill, load its main
instructions, and load the required visual UX references for the current task:

- visual quality checklist;
- product-category playbook;
- visual validation protocol;
- accessibility and perceived-performance polish guidance.

If the skill cannot be resolved, read, or attached to the UX agent context, the
UX lane must fail closed with a visible `ux_skill_unavailable` state. It must
not silently fall back to a generic UX prompt.

## Agent Model

### `ux_generator`

`ux_generator` is a Senior UX Codex. It must have the `visual-ux-polish` skill
associated as a required skill and must explicitly follow the skill before
making UX changes.

Responsibilities:

- identify product type, audience, platform, user roles, and top tasks;
- create or update the project UX brief;
- run benchmark research for the product category when internet or local
  references are available;
- inspect the real app with screenshots across required viewports;
- improve first-time experience, navigation, visual hierarchy, responsive
  behavior, empty/loading/error states, forms, microcopy, touch targets, focus,
  perceived performance, and accessibility;
- preserve existing components, tokens, icons, and platform conventions;
- create or update lightweight UAT scenarios from product requirements;
- run or request visual validation, accessibility checks, widget tests, and
  smoke checks relevant to the touched UI;
- write UX evidence before handing off to `ux_reviewer`.

`ux_generator` must not:

- change backend endpoints, migrations, auth, persistence, domain models,
  business rules, release configuration, secrets, or preview API data paths;
- introduce mock/demo/local data into release paths;
- change functional workflow outcomes without an explicit Domain Factory task;
- hide broken functionality behind visual copy or decoration.

If a UX fix requires functionality, the agent must emit a structured
`functional_dependency` recommendation for Domain Factory instead of
implementing it.

### `ux_reviewer`

`ux_reviewer` is an independent UX reviewer. It also requires the
`visual-ux-polish` skill.

Responsibilities:

- read the same UX brief, benchmark notes, screenshots, UAT scenarios, and app
  context as `ux_generator`;
- review the UX generator diff for scope violations and UX regressions;
- compare before/after screenshots at required viewports;
- verify first-time comprehension, primary action clarity, hierarchy,
  responsive behavior, accessibility, state quality, touch targets, focus, copy,
  and consistency with the product domain;
- verify that functional behavior and backend contracts were not changed;
- classify findings as `blocker`, `major`, `minor`, or `polish`;
- return a concrete continuation prompt to `ux_generator` when issues remain;
- mark the UX lane complete only when evidence proves the UI is ready for the
  current stage.

`ux_reviewer` can request more UX work but does not implement product changes
unless explicitly configured in a future mode.

## Required UX Knowledge

Both UX agents must reason about:

- first-run comprehension: what a new user understands in the first viewport and
  what action they know to take next;
- information architecture: navigation labels, sections, task grouping,
  discoverability, back paths, role-specific views, and content priority;
- interaction design: input controls, modes, validation, feedback, undo/retry,
  disabled states, destructive actions, and keyboard/touch behavior;
- visual design: layout, hierarchy, spacing, typography, color, density,
  alignment, iconography, motion, and media relevance;
- mobile ergonomics: thumb reach, tap target spacing, bottom bars, sheets,
  keyboard overlap, narrow width, and large text;
- desktop productivity: scanning, filters, tables/lists, bulk actions, stable
  toolbars, split panes, and efficient repeated actions;
- accessibility: WCAG AA contrast, focus visibility, focus not obscured, target
  size, labels, semantic roles, keyboard order, reduced motion, zoom/text
  scaling, and non-color-only states;
- perceived performance: skeletons, stable dimensions, partial loading,
  optimistic feedback, layout shift, saved/error states, and retry paths;
- content quality: concrete labels, button verbs, error recovery, empty states,
  placeholders vs. labels, status language, and translation/long-string risk;
- trust and professionalism: polish, consistency, predictable patterns,
  appropriate domain tone, and removal of generic template feel;
- UAT readiness: realistic task scripts, expected results, role coverage,
  edge-case data, and observable pass/fail evidence.

## Benchmark Contract

Before substantial UX changes, `ux_generator` must produce a benchmark note.

Required inputs:

- product category and target platform;
- 5 to 8 comparable products, design systems, screenshots, or local references;
- a distinction between direct competitors, indirect workflow substitutes, and
  platform/design-system references;
- patterns extracted from references: navigation, density, tables/lists,
  forms, first-run flow, empty states, error handling, mobile behavior,
  typography, CTA hierarchy, and trust signals;
- explicit rejected patterns when they conflict with the product task.

If internet is unavailable, the note must say so and use local references,
existing screenshots, design systems, and product-category playbooks.

Benchmark output is stored as:

```text
.codex/ux/benchmark.md
.codex/ux/references/
```

Agents must use benchmarks as calibration only. The implementation must remain
original and consistent with the generated app's own product identity.

## Screenshot And Evidence Contract

Every UX lane pass must produce shared evidence that both UX agents can read.

Required screenshots:

- before and after screenshots for changed primary screens;
- mobile narrow: `390x844` or `360x800`;
- mobile large: `430x932` or `414x896`;
- tablet: `768x1024`;
- desktop: `1440x900` or `1365x768`;
- wide desktop for dashboards, tables, maps, editors, or canvas-heavy products.

Required mechanical checks when the app can run:

- no accidental horizontal overflow;
- no obvious clipping or element outside viewport;
- interactive targets meet platform minimums or have adequate spacing;
- focus-visible is present and not hidden by sticky content;
- loading, empty, error, disabled, hover, selected, and pressed states do not
  resize or break layout;
- fixed bars, toasts, sheets, drawers, and virtual keyboard states do not hide
  critical actions.

Evidence output is stored as:

```text
.codex/ux/
  ux-brief.md
  benchmark.md
  uat-scenarios.md
  visual-audit.json
  ux-generator-report.md
  ux-reviewer-report.md
  screenshots/
```

The backend should attach this evidence to the agent run record so the chat UI
can expose it.

## UAT Contract

The UX lane owns lightweight UX/UAT preparation, not full business acceptance.

`ux_generator` must derive UAT scenarios from the approved project/domain
contract:

- primary first-time task;
- one task per major user role;
- empty-state first action;
- happy-path create/update/read flow;
- error or blocked-permission flow;
- mobile narrow flow;
- returning-user flow when state exists.

Each scenario must include:

- persona or role;
- preconditions and test data;
- steps in user language;
- expected result;
- UX acceptance signals: task can be discovered, completed, understood, and
  recovered from;
- pass/fail status or `not_run`;
- screenshots or notes.

Agent-run UAT can be a proxy walkthrough. Real human UAT, when available, must
be recorded separately and should override agent assumptions.

## Flow Integration

### New Project Intake: Lightweight UX Generator

After guided intake and before final build approval:

1. The system runs only `ux_generator` in lightweight planning mode.
2. The system derives a `ux_brief` from the project contract.
3. `ux_generator` may ask only UX-critical missing questions:
   audience, first task, tone, visual references, platform priority,
   accessibility constraints, and must-have first-run outcomes.
4. The approved contract stores the UX brief as part of project scope.
5. No code is changed during this pass.

### Post-Project-Factory UX Pass

After deterministic init produces a baseline:

```text
baseline_generator -> baseline_reviewer -> ux_generator -> ux_reviewer
```

The UX pass focuses on first experience, shell navigation, empty states,
responsive layout, theme, copy, and perceived product quality.

This is the final automatic stage of the New Project creation task. When
`ux_reviewer` returns `complete`, the task is done.

### Domain Factory UX Sequence

Domain Factory does not add a second functional generator after the domain
modeling step. Its implementation mode is already the paired
`domain_generator -> domain_reviewer` workflow.

The automatic Domain Factory UX sequence is:

```text
domain brief captured
-> UX Generator
-> UX Reviewer
-> UX Generator
-> Domain Factory Generator
-> Domain Reviewer
-> UX Generator <-> UX Reviewer, max 10 passes
```

The early UX baseline must be based on the user's actual domain brief, not on a
generic scaffold. Domain Factory generator and reviewer prompts must carry that
UX direction forward while they implement and review the functional domain.

Validation for this spec does not require running a live throwaway project. It
must verify implementation wiring instead:

- Domain Factory context reports `automaticDomainFactoryUx=true`.
- Domain Factory state and intake contract expose the early UX baseline, domain
  implementation, and final UX polish stages.
- The Project Factory runner harness executes the early UX baseline order before
  implementation and then the final UX generator/reviewer loop after it.
- Workflow evidence exposes the explicit full agent order and keeps
  `domain_generator -> domain_reviewer` as the only functional implementation
  pair.
- No `functional_generator`, extra app generator stage, or misleading
  `disabled_by_configuration` UX state appears in Domain Factory status.
- Domain generator prompt requires consuming the configured UX workflow.
- Final UX polish is capped at 10 passes with reviewer-controlled early stop.

### Manual Slash UX Passes

The user can invoke UX later through slash commands in an existing project.

#### `/ux`

Runs `ux_generator` only.

- Intended for a direct UX pass over the current project state.
- Uses the required `visual-ux-polish` skill.
- Can inspect, benchmark, capture screenshots, improve UI, and record evidence.
- Does not require a reviewer loop.
- Must keep the same no-functionality boundary.

#### `/ux-full`

Runs the full UX lane:

```text
ux_generator -> ux_reviewer -> ux_generator -> ux_reviewer -> ...
```

- Default maximum iterations: `15`.
- `ux_reviewer` owns the stop condition.
- If the reviewer approves after 2 passes, the lane stops after 2 passes.
- If the reviewer finds issues, it sends a continuation prompt back to
  `ux_generator`.
- The lane stops when reviewer returns `complete`, `blocked`, or the iteration
  limit is reached.
- This command is for long, deep UX work over an already-created project.

### Manual Pre-Release UX Gate

When the user explicitly invokes `/ux-full` before preview release readiness:

```text
tests/smoke -> ux_generator final polish if needed -> ux_reviewer gate
```

The release cannot claim UX-ready if:

- required screenshots are missing without a recorded limitation;
- `ux_reviewer` has unresolved blocker or major findings;
- the UX diff changed protected functional areas;
- the app has clear mobile overflow, clipped primary action, inaccessible
  focus, unreadable contrast, or broken empty/error/loading states;
- UAT scenarios for primary role/task are missing.

## Scope Boundary

Allowed UX paths include project-local frontend and visual assets:

- Flutter screens, widgets, routes, visible text, theme, tokens, icons, assets,
  widget/golden tests, integration smoke, and UX evidence;
- web frontend screens, components, CSS, tokens, visual tests, Playwright
  screenshots, and UX evidence;
- generated project SDD files that document UX requirements and evidence.

Disallowed UX paths include:

- backend domain behavior, endpoints, repositories, migrations, auth, RBAC,
  persistence, release scripts, updater configuration, secrets, CI publishing,
  Bridge control-plane internals, and generated project identity.

The backend should enforce scope by file allow/deny rules where possible and
the reviewer must independently flag any violation.

## Data And Release Rules

- UX validation must use real preview/backend configuration for release paths.
- Mock, demo, seeded-local, or placeholder data can be used only when the user
  explicitly asks for a demo/mock build.
- UX agents may create visual fixtures for local validation only if they are
  clearly labeled as non-release evidence.
- Any release-facing screenshot must state the backend/runtime used.
- UX cannot mark release readiness if API URLs, app updater defines, or preview
  runtime paths were changed outside explicit release work.

## Agent Prompt Contract

`ux_generator` prompt must include:

- required skill: `visual-ux-polish`;
- current project/session/workspace identity;
- product contract and UX brief;
- protected functional boundaries;
- allowed UI/design paths;
- benchmark and screenshot requirements;
- UAT scenario requirements;
- evidence output locations;
- instruction to modify UI directly and validate;
- instruction to emit `functional_dependency` instead of changing backend or
  business behavior.

`ux_reviewer` prompt must include:

- required skill: `visual-ux-polish`;
- original UX brief and product contract;
- benchmark notes and all screenshots;
- diff summary and touched files;
- scope boundary checklist;
- severity taxonomy;
- strict response schema:

```json
{
  "status": "complete|continue|blocked",
  "summary": "short UX readiness summary",
  "findings": [
    {
      "severity": "blocker|major|minor|polish",
      "location": "screen, viewport, file, or artifact",
      "evidence": "screenshot/check/observable condition",
      "impact": "why it matters",
      "fix": "specific next UX action"
    }
  ],
  "continuation_prompt": "next prompt for ux_generator, required unless complete",
  "scope_violations": ["protected area changed or empty"],
  "release_gate": "pass|fail"
}
```

## Backend And UI Contract

The agent configuration model must support `ux_generator` and `ux_reviewer` as
configurable agent ids and types.

The product should expose UX lane state in the chat/workbench:

- pending UX brief;
- running UX generator;
- awaiting UX reviewer;
- needs UX changes;
- UX approved;
- UX blocked with evidence.

The UI should show UX artifacts compactly:

- benchmark summary;
- screenshot set;
- UAT scenario list;
- reviewer findings;
- pass/fail gate.

Existing `generator_only`, `generator_reviewer`, triad, and supervisor presets
must keep working. New Project and Domain Factory can opt into the UX lane
without forcing all generic chats to use it.

## Acceptance Criteria

- `ux_generator` and `ux_reviewer` are first-class configurable agents.
- Both UX agents require `visual-ux-polish`.
- New Project runs a lightweight `ux_generator` pass before Project Factory
  baseline generation.
- The lightweight pass creates UX direction but does not modify code.
- Project Factory baseline completion triggers `ux_generator -> ux_reviewer`.
- Automatic New Project work stops after the post-baseline UX reviewer approves
  or blocks.
- `/ux` can trigger a manual UX generator-only pass in the current project.
- `/ux-full` can trigger a manual UX generator/reviewer loop with default max
  iterations of 15 and reviewer-controlled stop.
- UX evidence includes benchmark notes, screenshots, UAT scenarios, generator
  report, reviewer report, and validation status.
- UX agents can modify UI and visual assets but cannot modify protected backend,
  persistence, auth, RBAC, release, or runtime configuration areas.
- UX reviewer can return `continue` with a concrete prompt until UX gate passes.
- Release readiness fails on unresolved UX blocker/major findings.
- UX blocked states are explicit and actionable.
- Tests cover agent configuration, prompt generation, lane sequencing, evidence
  persistence, UI state rendering, and scope enforcement.
