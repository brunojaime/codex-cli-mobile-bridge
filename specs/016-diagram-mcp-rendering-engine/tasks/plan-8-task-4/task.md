# T041 Prepare and publish frontend release

Spec: 016-diagram-mcp-rendering-engine

Plan: MCP Diagram Workflow And Mobile Release

Status: completed

- [x] T041 Prepare and publish frontend release.

## Acceptance Notes

- The mobile app version is bumped after diagram viewing is implemented and tested.
- Android release uses the standard tag workflow with real backend URL and updater configuration.
- Release notes mention MCP-rendered diagram viewing and any known limitations.
- The HTTP Tailnet release URL is permitted by a narrow Android network security config and requires Tailnet/MagicDNS access on the phone unless a public HTTPS bridge URL is configured.

## Implementation Notes

- Follow the codex-cli-mobile-bridge release policy: no mock/demo backend for a user-installable release unless explicitly requested.
- Verify the backend endpoint and mobile build before publishing.
