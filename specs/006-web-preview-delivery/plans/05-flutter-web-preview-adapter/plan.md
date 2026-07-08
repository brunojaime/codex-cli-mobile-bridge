# Flutter Web Preview Adapter

Update generated Flutter templates so the web build can run against the shared
preview runtime.

Generated app config must support:

```text
APP_RUNTIME_PROFILE=preview
API_RUNTIME=cloudflare_preview
API_BASE_URL=https://preview.nienfos.com
APP_SLUG=<app-slug>
```

The Flutter API client must use Preview API v1 for preview mode and must not
call FastAPI-only endpoints in the preview path.
