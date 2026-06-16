---
name: onenote-connect
description: Use this skill when a user wants to connect Codex to Microsoft OneNote through delegated Microsoft Graph auth, inspect notebooks or sections, create pages from HTML or text, or upload images and file attachments into OneNote pages.
---

# OneNote Connect

## Overview

This skill provides a deterministic CLI for OneNote workflows that do not fit ad hoc prompting well: delegated sign-in, notebook and section discovery, page creation, multipart uploads, and page updates.

Use it for requests such as:

- connect my OneNote account
- list my notebooks or sections
- create a OneNote page from these notes
- upload these screenshots and PDFs into a OneNote page
- append this HTML summary to an existing OneNote page

## Workflow

1. Read [auth-setup.md](./references/auth-setup.md) if the Microsoft Entra app is not configured yet.
2. Install or update the skill under `~/.codex/skills`.
3. Use `list-cached-accounts` to inspect locally cached identities before reconnecting or choosing a `--login-hint`.
4. Authenticate with the CLI and cache a delegated token.
5. Use `list-notebooks --name-contains <text> --limit <n>` and `list-sections --notebook <id> --name-contains <text> --limit <n>` to narrow the notebook and section first when discovery output is large.
6. Use `list-pages --section <id> --title-contains <text> --sort modified --descending --limit <n>` to discover the page you want to edit quickly when a section has many pages.
7. Use `get-page-content --page <id> --include-ids` to inspect the current HTML and element IDs.
8. Use `replace-page-content --page <id> --target <element-id>` for precise text/HTML edits against a discovered element.
9. Use `replace-page-with-assets --page <id> --target <element-id> --asset <path>` when the replacement includes files or images.
10. Create or update pages through the CLI instead of hand-building Graph requests.

## Install

Install the skill into Codex before using it.

Use symlink mode when you are actively developing from this repo and want the installed skill to track local edits:

```bash
python skills/onenote-connect/scripts/install_skill.py
```

Use copy mode when you want a standalone installed snapshot that keeps working even if the repo moves later:

```bash
python skills/onenote-connect/scripts/install_skill.py --mode copy
```

Preview changes without touching the filesystem:

```bash
python skills/onenote-connect/scripts/install_skill.py --dry-run
```

For automation or CI wrappers, add `--json` to the installer commands:

```bash
python skills/onenote-connect/scripts/install_skill.py --dry-run --json
```

Remove the installed skill cleanly when you no longer need it:

```bash
python skills/onenote-connect/scripts/install_skill.py --uninstall
```

Preview uninstall without deleting anything:

```bash
python skills/onenote-connect/scripts/install_skill.py --uninstall --dry-run
```

Run a read-only real-tenant smoke test that verifies auth plus discovery without mutating tenant state:

```bash
uv run --with msal python skills/onenote-connect/onenote_smoke_test.py --client-id "$ONENOTE_CLIENT_ID"
```

For CI or wrapper tooling, add `--json` to receive structured smoke-test output:

```bash
uv run --with msal python skills/onenote-connect/onenote_smoke_test.py --client-id "$ONENOTE_CLIENT_ID" --json
```

Run the opt-in write smoke test only when you are comfortable creating one page in a section and appending to one existing page:

```bash
uv run --with msal python skills/onenote-connect/onenote_smoke_test.py --client-id "$ONENOTE_CLIENT_ID" --write --write-section <section-id> --write-page <page-id>
```

## Commands

Run the CLI from the repo:

```bash
uv run --with msal python skills/onenote-connect/onenote.py connect --auth-flow device-code
```

Primary commands:

- `connect`
- `clear-auth`
- `whoami`
- `list-cached-accounts`
- `list-notebooks --name-contains <text> --limit <n>`
- `list-sections --notebook <id> --name-contains <text> --limit <n>`
- `list-pages --section <id> --title-contains <text> --sort modified --descending --limit <n>`
- `get-page-content --page <id> --include-ids`
- `replace-page-content --page <id> --target <element-id> --html-file <path>`
- `replace-page-with-assets --page <id> --target <element-id> --asset <path> ...`
- `create-page --section <id> --title <title> --html-file <path>`
- `create-page-with-assets --section <id> --title <title> --html-file <path> --asset <path> ...`
- `append-page --page <id> --html-file <path>`
- `attach-to-page --page <id> --file <path> ...`

The CLI also accepts `--text-file` or inline `--content` when you do not want to prepare HTML by hand.

## Implementation Notes

- Auth is delegated user auth through MSAL public-client flows.
- Device-code is the safest default for terminal-first usage.
- Browser interactive auth is available when the app registration allows `http://localhost`.
- Token cache is stored locally and reused for silent refresh.
- Multipart page creation uses a `Presentation` part.
- Multipart page updates use a `Commands` part.
- The Graph endpoint details are documented in [graph-endpoints.md](./references/graph-endpoints.md).
