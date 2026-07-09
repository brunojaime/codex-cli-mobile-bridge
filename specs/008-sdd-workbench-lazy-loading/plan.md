# SDD Workbench Lazy Loading Plan

## Plan 1: Contract And Compatibility

- Define summary/detail endpoint behavior.
- Preserve the legacy full snapshot endpoint.
- Define fallback behavior for older backends.

## Plan 2: Backend API

- Add service methods for lightweight project summaries and single-spec detail.
- Add API schemas/endpoints for summary and detail.
- Optimize diagram listing so it avoids full plan/task reads.

## Plan 3: Workbench Client

- Add summary/detail methods to `SddExplorerClient`.
- Load summary first from `SddExplorerPanel`.
- Hydrate selected specs on demand and cache them in memory.
- Show per-spec loading/error/retry UI.

## Plan 4: Validation And Release

- Add backend tests for summary/detail/fallback compatibility.
- Add Workbench tests for lazy request order and spec hydration.
- Run backend, package, and mobile tests.
- Publish a Codex Mobile Android release with real backend configuration.

