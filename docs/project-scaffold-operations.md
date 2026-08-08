# Composable Project Scaffold Operations

`creation.mode=scaffold` creates only a neutral technical foundation. The
existing Product flow remains the default while the rollout flag is disabled.

## Create and recover a scaffold

1. Enable `PROJECT_SCAFFOLD_ENABLED=true` on a test Bridge deployment. Keep
   `PROJECT_SCAFFOLD_REMOTE_WRITES_ENABLED=false` for a local-only rollout.
2. In New Project choose **Scaffold**, then select mobile, web, API,
   Cloudflare, and AWS independently. GitHub owner and an initial admin email
   appear only when the selected remote/protected-preview behavior needs them.
3. Review the exact remote effects. The confirmation explicitly records that
   Domain Factory, UX, D1, Android publication, installable registration, and
   `terraform apply` will not run.
4. A successful job ends at `scaffold_ready`. Missing credentials or external
   failures end at `scaffold_blocked_with_context`; the local workspace and
   exact retry actions remain available. Fix the reported prerequisite and use
   **Retry**. Completed phases are idempotent and are not regenerated.

When `PROJECT_SCAFFOLD_EXECUTE_COMMANDS=false`, generated targets, validation,
and the baseline commit remain explicitly blocked/prepared rather than being
reported as ready. Enable execution and retry to create locks/native sources,
run builds, and commit the clean baseline. Requested GitHub or Cloudflare writes
also require `PROJECT_SCAFFOLD_REMOTE_WRITES_ENABLED=true`. GitHub verification
uses authenticated `gh repo view` before attempting creation; an unauthenticated
404 is never treated as proof that a private repository is absent.

The durable result is `.codex/factory/scaffold-result.json`; the handoff is
`.codex/factory/scaffold-context.md`. Workbench discovers the workspace through
`codex-bridge.yaml`. It remains Bridge-owned and is never added to product
navigation.

## Start Product

Choose **Start Product** only from `scaffold_ready`, after reviewing the
scaffold result. A blocked scaffold must be retried first. This is the sole
action that enters `domain_intake`. Domain Factory reuses the same
workspace, manifest targets, repository, Cloudflare resource, Workbench scope,
and context pack. It owns the later product decisions: navigation, visual
design, auth, roles, persistence, feedback/updater integration, and releases.

## Cloudflare and AWS

- `generate_only` writes configuration and performs zero remote calls.
- `provision_scaffold` may deploy only the neutral project-scoped scaffold.
  It reports API/product/production/installable readiness as false and D1 as
  disabled.
- A protected preview is never silently downgraded to public access. Because
  the existing invite/access contract requires persistence, the D1-free
  scaffold stops with `protected_preview_access_not_configured` until a
  separately reviewed access/persistence setup is authorized.
- `architecture_docs_only` records undecided AWS choices.
- `terraform_ready` writes a resource-neutral foundation, then may run
  `terraform fmt -check`, `terraform init -backend=false`, and
  `terraform validate`. Scaffold never plans or applies infrastructure.

Any later AWS apply, D1 provisioning, production deployment, APK publication,
or Bridge installable registration is a separate explicit Product/release
operation. Productive releases must use real non-local configuration and must
not contain placeholders, seeded users, or mock/demo data unless the user
explicitly requests a clearly labeled demo release.

Android release adapters remove temporary workspace copies of keystores and
`key.properties` after every build attempt. Canonical signing material remains
only in the Bridge-owned ignored secrets directory.
