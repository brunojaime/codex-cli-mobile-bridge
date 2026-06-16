# OneNote Auth Setup

## Required App Registration Settings

- Register a Microsoft Entra public client application.
- Add delegated Microsoft Graph permissions:
  - `Notes.ReadWrite`
  - `User.Read`
  - `offline_access`
  - `openid`
  - `profile`
- Enable public client flows.
- If you want browser-based login, add `http://localhost` as a redirect URI.

## Runtime Configuration

The CLI reads these values from flags or environment variables:

- `ONENOTE_CLIENT_ID`
- `ONENOTE_TENANT_ID`
- `ONENOTE_AUTHORITY_BASE`
- `ONENOTE_SCOPES`
- `ONENOTE_TOKEN_CACHE_PATH`

Example:

```bash
export ONENOTE_CLIENT_ID="00000000-0000-0000-0000-000000000000"
export ONENOTE_TENANT_ID="common"
uv run --with msal python skills/onenote-connect/scripts/onenote_cli.py connect --auth-flow device-code
```

The token cache defaults to:

```text
~/.config/codex/onenote-connect/token-cache.json
```

The CLI writes the cache with user-only permissions when the platform allows it.
