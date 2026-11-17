from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient

from backend.app.infrastructure.realtime.job_stream_hub import JobStreamHub


class _FakeService:
    def __init__(self, fingerprints):
        self._fingerprints = list(fingerprints)

    def session_fingerprint(self, session_id):
        if len(self._fingerprints) > 1:
            return self._fingerprints.pop(0)
        return self._fingerprints[0]


def _app(service):
    app = FastAPI()
    hub = JobStreamHub(poll_interval_seconds=1)

    @app.websocket("/ws/sessions/{session_id}")
    async def endpoint(websocket: WebSocket, session_id: str):
        await hub.stream_session(
            websocket,
            session_id=session_id,
            service=service,
            check_interval_seconds=0.01,
            heartbeat_seconds=0.05,
        )

    return app


def test_session_stream_pushes_only_on_change_then_heartbeats():
    service = _FakeService(["a", "a", "b", "b"])
    with TestClient(_app(service)).websocket_connect("/ws/sessions/s1") as ws:
        assert ws.receive_json() == {"type": "session.ready", "session_id": "s1"}
        assert ws.receive_json() == {"type": "session.changed", "session_id": "s1"}
        assert ws.receive_json() == {"type": "ping"}


def test_session_stream_reports_missing_session():
    service = _FakeService([None])
    with TestClient(_app(service)).websocket_connect("/ws/sessions/gone") as ws:
        assert ws.receive_json() == {"type": "session.missing", "session_id": "gone"}
