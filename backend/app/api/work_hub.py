"""Route the three intake paths to one configured coordinator, without a second queue."""

from __future__ import annotations

from urllib.parse import urlsplit

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse, Response


def install_work_hub(app, settings, *, transport=None):
    url = getattr(settings, "work_hub_url", "").rstrip("/")
    if not url or settings.bridge_environment != "prod":
        return
    target = urlsplit(url)
    if (
        target.scheme not in {"http", "https"}
        or not target.hostname
        or target.username
        or target.password
        or target.query
        or target.fragment
    ):
        raise ValueError("WORK_HUB_URL must be an HTTP(S) origin without credentials")
    own_port = settings.api_port
    if (
        target.hostname in {"127.0.0.1", "localhost", "::1"}
        and (target.port or 80) == own_port
    ):
        raise ValueError("WORK_HUB_URL must not point back to this backend")

    @app.middleware("http")
    async def forward_work(request: Request, call_next):
        path = request.url.path.removeprefix("/api/v1")
        forward = path == "/work" or path.startswith("/work/")
        if path == "/feedback-batches/start-session" and request.method == "POST":
            try:
                payload = await request.json()
                forward = (
                    isinstance(payload, dict)
                    and payload.get("executionMode", payload.get("execution_mode"))
                    == "backlog"
                )
            except (ValueError, UnicodeDecodeError):
                pass
        if not forward:
            return await call_next(request)
        if request.headers.get("x-bridge-work-hop"):
            return JSONResponse(
                {"detail": "Se detectó un ciclo en el coordinador"}, status_code=503
            )
        try:
            async with httpx.AsyncClient(
                transport=transport, timeout=90, follow_redirects=False, trust_env=False
            ) as client:
                response = await client.request(
                    request.method,
                    url + path,
                    params=request.query_params.multi_items(),
                    content=await request.body(),
                    headers={
                        "content-type": "application/json",
                        "x-bridge-work-hop": "1",
                    },
                )
            if response.is_redirect:
                return JSONResponse(
                    {"detail": "El coordinador devolvió una redirección inesperada"},
                    status_code=503,
                )
            return Response(
                response.content,
                status_code=response.status_code,
                media_type="application/json",
            )
        except httpx.HTTPError:
            return JSONResponse(
                {
                    "detail": "El coordinador está reiniciando. Conservá el pedido y reintentá con su misma identidad."
                },
                status_code=503,
            )
