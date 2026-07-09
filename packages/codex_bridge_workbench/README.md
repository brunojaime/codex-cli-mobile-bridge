# Codex Bridge Workbench

Reusable Flutter package for the Codex Mobile Bridge Architecture Workbench.

It provides:

- read-only SDD dashboard and explorer UI
- SDD API client and project models
- local Mermaid preview rendering through bundled Mermaid JS
- feedback and Codex action composer abstractions

The consuming app owns all runtime wiring:

- Bridge base URL
- workspace selection/current project behavior
- `CODEX_BRIDGE_DEV_MODE`
- feedback queue callback
- Codex/message callback

This package must not contain mock data, placeholder URLs, release shortcuts, or
app-specific navigation behavior.

## Minimal Integration

Add the package as a repo-local dependency from the consuming Flutter app:

```yaml
dependencies:
  codex_bridge_workbench:
    path: ../codex-cli-mobile-bridge/packages/codex_bridge_workbench
```

Wrap the app from `MaterialApp.builder`. The host app owns the Bridge URL,
current workspace path, and real submit callbacks:

```dart
const codexBridgeDevMode = bool.fromEnvironment('CODEX_BRIDGE_DEV_MODE');
const apiBaseUrl = String.fromEnvironment('API_BASE_URL');
const workspacePath = String.fromEnvironment('CODEX_BRIDGE_WORKSPACE_PATH');

MaterialApp(
  builder: (context, child) {
    final app = child ?? const SizedBox.shrink();
    return CodexBridgeDevModeWrapper(
      enabled: codexBridgeDevMode,
      bridgeUrl: apiBaseUrl,
      workspacePath: workspacePath,
      sddFeedbackSubmitter: submitFeedbackToBridge,
      sddActionSubmitter: sendCodexActionToBridge,
      child: app,
    );
  },
);
```

When `CODEX_BRIDGE_DEV_MODE` is false, the wrapper returns `child` unchanged.
Apps should pass their current project workspace path. Bridge/control apps may
omit `workspacePath` to use the Bridge server default project selection.

## Release Safety

Production or user-installable releases must use real Bridge configuration and
real workspace paths. Do not enable mock data, seeded demo state, placeholder
URLs, or local demo shortcuts unless a release is explicitly marked as a demo.
The package does not provide fallback API URLs or fallback workspaces; the host
app must supply them.

## Mermaid Rendering

Mermaid source files (`.mmd`) are the source of truth. This package renders them
locally in the client with Mermaid JS bundled as a Flutter asset:

- asset path: `assets/vendor/mermaid/mermaid.min.js`
- asset package path used at runtime:
  `packages/codex_bridge_workbench/assets/vendor/mermaid/mermaid.min.js`
- Mermaid version: 11.16.0
- Mermaid license: MIT

Rendering uses `webview_flutter` and a hardened local HTML payload. The payload
sets Mermaid `securityLevel: 'strict'`, base64-encodes diagram source before it
enters JavaScript, blocks external navigation, and does not require backend
rendering, CDN access, or shell commands. Host Android/iOS builds must include
the normal WebView platform support required by `webview_flutter`.
