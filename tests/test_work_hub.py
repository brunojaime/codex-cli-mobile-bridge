from types import SimpleNamespace
import json

import httpx
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from fastapi.middleware.cors import CORSMiddleware
import pytest

from backend.app.api.work_hub import install_work_hub


def build(transport, environment="prod"):
    app = FastAPI()

    @app.post("/feedback-batches/start-session")
    async def feedback(request: Request):
        return {"local_execute": await request.json()}

    @app.get("/work")
    def work():
        return {"local": True}

    install_work_hub(
        app,
        SimpleNamespace(
            work_hub_url="http://127.0.0.1:8118",
            bridge_environment=environment,
            api_port=8000,
        ),
        transport=transport,
    )
    app.add_middleware(CORSMiddleware, allow_origins=["https://product.example"], allow_methods=["*"], allow_headers=["*"])
    return TestClient(app)


def test_all_three_entries_use_same_hub_without_forwarding_credentials():
    requests = []

    def respond(request):
        requests.append(request)
        assert "authorization" not in request.headers
        assert "cookie" not in request.headers
        return httpx.Response(202, json={"backlogId": "same-durable-queue"})

    client = build(httpx.MockTransport(respond))
    payload = {
        "source": "whatsapp",
        "source_key": "stable",
        "instruction": "Cambiar texto",
    }
    assert client.post(
        "/api/v1/work/backlog",
        json=payload,
        headers={"authorization": "unrelated-product-token", "origin": "https://product.example"},
    ).json()["backlogId"]
    assert json.loads(requests[0].content) == payload
    assert requests[0].url.path == "/work/backlog"
    feedback = {
        "executionMode": "backlog",
        "batchId": "stable-feedback",
        "items": [{"comment": "Mantener captura"}],
    }
    assert (
        client.post("/feedback-batches/start-session", json=feedback).status_code == 202
    )
    assert json.loads(requests[1].content) == feedback
    assert client.post(
        "/feedback-batches/start-session", json={"executionMode": "execute"}
    ).json()["local_execute"]
    assert len(requests) == 2
    assert client.get("/work", headers={"x-bridge-work-hop": "1"}).status_code == 503


def test_dev_keeps_coordinator_local_and_outage_returns_retryable_failure():
    def unavailable(request):
        raise httpx.ConnectError("offline", request=request)

    transport = httpx.MockTransport(unavailable)
    assert build(transport, "dev").get("/work").json() == {"local": True}
    response = build(transport).post(
        "/work/backlog", json={"source_key": "keep-this-key"}
    )
    assert response.status_code == 503
    assert "misma identidad" in response.json()["detail"]


def test_hub_cannot_proxy_back_to_itself():
    with pytest.raises(ValueError):
        install_work_hub(
            FastAPI(),
            SimpleNamespace(
                work_hub_url="http://127.0.0.1:8000",
                bridge_environment="prod",
                api_port=8000,
            ),
        )


def test_forwarded_responses_keep_cors_for_feedback_consumers():
    client = build(httpx.MockTransport(lambda _: httpx.Response(202, json={'backlogId':'one'})))
    response = client.post('/feedback-batches/start-session',json={'executionMode':'backlog'},headers={'origin':'https://product.example'})
    assert response.headers['access-control-allow-origin'] == 'https://product.example'
