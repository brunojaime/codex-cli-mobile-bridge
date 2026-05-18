# Repo MCP App Contract

Repo-local MCP apps live under:

```text
mcp_apps/<module_name>/
  __init__.py
  server.py
  app.json
```

Typical convention:

- `app_id`: kebab-case, for example `project-catalog`
- `module_name`: underscore form used by Python imports, for example `project_catalog`

`app.json` fields used by this repo:

```json
{
  "app_id": "my-app",
  "name": "My App",
  "description": "Short description",
  "recommended_server_id": "my-app",
  "transport": "stdio",
  "command": "uv",
  "args": [
    "run",
    "--project",
    "{repo_root}",
    "python",
    "-m",
    "mcp_apps.my_app.server"
  ],
  "env": {
    "PROJECTS_ROOT": "{projects_root}"
  },
  "supports_ui_extension": false,
  "ui_entry_uri": null,
  "tags": ["tag-a", "tag-b"],
  "preview_tool": {
    "name": "list_items",
    "arguments": {
      "limit": 5
    }
  }
}
```

Template values resolved by the backend:

- `{repo_root}`
- `{projects_root}`

Discovery behavior:

- backend scans `mcp_apps/*/app.json`
- backend launches the declared server over stdio
- backend calls `initialize`, `tools/list`, `resources/list`, `prompts/list`
- if `preview_tool` exists, backend calls it and exposes the result to the frontend

Install behavior:

- frontend calls `POST /codex/mcp-apps/{app_id}/install`
- backend compares the installed Codex server config with the repo app spec using `codex mcp get --json`
- backend reconciles drift by removing and re-adding the server when transport, command, args, or env differ
- backend runs `codex mcp add <recommended_server_id> ...` for missing servers
- installed servers appear in `codex mcp list`
- repo MCP apps do not declare `cwd` because the Codex CLI install flow does not persist that field today

Current frontend support:

- app metadata
- preview data
- install action
- enable server for current Codex run

Current frontend non-support:

- sandboxed iframe host for full `io.modelcontextprotocol/ui` rendering
