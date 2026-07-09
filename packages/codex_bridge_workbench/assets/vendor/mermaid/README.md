# Mermaid Runtime Asset

- Package: `mermaid`
- Version: `11.16.0`
- Source: `https://registry.npmjs.org/mermaid/-/mermaid-11.16.0.tgz`
- Bundled file: `package/dist/mermaid.min.js`
- License: MIT, copied to `LICENSE`

This file is bundled so SDD diagram previews render locally inside the Flutter
app. Runtime rendering must not load Mermaid from a CDN, call the backend, or
execute shell commands.

## Dev Validation

Widget tests should exercise the SDD Explorer through the renderer abstraction
with a fake renderer because Flutter's native WebView is not available in the
standard widget test environment.

For real local Mermaid rendering validation, run:

```bash
flutter build apk --debug
flutter run --dart-define=CODEX_BRIDGE_DEV_MODE=true
```

Then open the SDD Explorer and switch a diagram to `Preview`. The preview should
render from this bundled `mermaid.min.js` asset, while `Source` remains available
for the same `.mmd` file.

The repo includes a suspicious-content validation diagram at
`specs/002-sdd-visual-workbench/diagrams/security-suspicious-content.mmd`.
It contains script-like labels and an external link directive. In dev mode it
must either render sanitized output or show a per-diagram Mermaid error; it must
not navigate away from the generated local WebView document.
