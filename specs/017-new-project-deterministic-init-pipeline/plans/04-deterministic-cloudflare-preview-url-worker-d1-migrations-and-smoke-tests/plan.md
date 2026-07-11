# Deterministic Cloudflare Preview URL Worker D1 Migrations And Smoke Tests

Move Cloudflare preview setup into the init pipeline so the LLM receives a real
preview URL, Preview API URL, Worker, and D1 status by default.

Status: completed

## Deterministic Pipeline Scope

- Cloudflare/wrangler/account/zone preflight.
- Preview URL and API URL calculation.
- Worker, route, assets, and non-secret env create-or-verify behavior.
- D1 create-or-verify behavior.
- Baseline migration application.
- Preview deploy verification and public smoke tests.

## Tasks

- [x] T016 Add Cloudflare preflight for wrangler, account, zone, route, Worker, D1, and required secrets.
- [x] T017 Implement deterministic preview URL and API URL calculation for `preview.nienfos.com/{slug}`.
- [x] T018 Implement Cloudflare Worker, route, assets, and non-secret env create-or-verify behavior.
- [x] T019 Implement D1 database create-or-verify and baseline migration application.
- [x] T020 Implement Cloudflare preview deploy verification for Worker updates, protected routes, static assets, cache headers, and MIME types.
- [x] T021 Implement web preview and Preview API smoke phases with persisted public evidence.
