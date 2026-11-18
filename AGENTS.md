# Codex Mobile Bridge Agent Notes

## Release Data Policy

Production or user-installable releases must use real backend configuration and
real data paths. Do not enable mock data, seeded demo state, local demo mode, or
placeholder API URLs in release builds unless the user explicitly asks for a
demo/mock APK.

For Codex Mobile Android releases, use the standard tag workflow from
`scripts/publish_android_release.sh` after bumping `frontend/mobile_app/pubspec.yaml`.
Before publishing, verify the workflow will build with the intended real
`API_BASE_URL`/bridge URL and app updater defines. If a release is specifically
for feedback/edit mode, keep the real backend URL and real workspace/update
configuration; feedback mode should not imply mock data.

If the user does request a mock/demo release, make that visible in the version
scope, release tag, and final report so it cannot be confused with a real-data
release.

<!-- codex-mobile-project-secrets -->
## Project secrets

Add or rotate credentials through the chat's **Secrets** panel. They are stored in the workspace `.env`; never ask the user to paste secret values into chat and never print or reveal them.


<!-- chatgpt-bridge-dev-policy -->
## Colaboración ChatGPT desde Bridge DEV — 03/11/2026

Bruno indicó que Bridge DEV consulta siempre el proyecto ChatGPT de Codex Bridge,
ID de producto codex-cli-mobile-bridge (alias codex-bridge), repositorio
brunojaime/codex-cli-mobile-bridge y destino
https://chatgpt.com/g/g-p-6aea4404bac4819180e6443dc3f2a5d4/project.
Cuando el contexto/BRIDGE_ENVIRONMENT sea dev, preparar con exchange.py prepare
--environment dev --project codex-bridge y registrar con
chatgpt_handoff.py --environment dev register. Cola local 8167; continuación por
Bridge8118 al MISMO chat DEV que recibió este pedido, no al chat prod original de
un handoff anterior. No sustituir dev por prod si hay un fallo. GitHub conserva
solicitud/commit/evidencia y entrega; no implica permiso para promoción a prod.
Sólo consultar cuando el usuario pida ChatGPT según la skill compartida.
<!-- /chatgpt-bridge-dev-policy -->
