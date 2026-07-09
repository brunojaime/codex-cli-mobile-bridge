# Manifest Contract

Define and test the project manifest model before any file-writing generator is
added.

- Add a pure project manifest planning service.
- Validate project name, slug, platforms, backend, business type, and target
  path under `PROJECTS_ROOT`.
- Include mandatory auth, RBAC, admin, notifications, Codex, SDD, and release
  defaults.
- Include Codex CLI creation workflow defaults of 20 generator/reviewer pairs.
- Keep seed admin values as environment variable names only.
- Prove validation is deterministic and write-free.
