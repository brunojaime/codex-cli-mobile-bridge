# Generated App Runtime Profile

Make generated Flutter apps able to run against preview from both web and
Android.

- Generate `APP_RUNTIME_PROFILE=preview`.
- Generate `API_RUNTIME=cloudflare_preview`.
- Generate preview `API_BASE_URL` and `APP_SLUG` defines.
- Route API clients through Preview API v1 in preview mode.
- Keep FastAPI production/staging clients separate.
- Prevent mock/local data paths from being compiled into preview releases as the
  primary runtime.
