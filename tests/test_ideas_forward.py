from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from services.whatsapp_ingest.ideas_forward import ATTEMPT_FILENAME, CONFIG_RELATIVE, ideas_config
from services.whatsapp_ingest.worker import SUBMISSION_FILENAME, TRIAGE_FILENAME, WhatsAppIntakeWorker
from tests.test_whatsapp_intake_worker import FakeBridge, FakeTriage, decision, settings, write_record


def ideas_project(projects_root: Path, config: dict) -> Path:
    workspace = projects_root / "ideas-proyectos"
    (workspace / CONFIG_RELATIVE).parent.mkdir(parents=True)
    (workspace / CONFIG_RELATIVE).write_text(json.dumps(config), encoding="utf-8")
    return workspace


class Pipeline(BaseHTTPRequestHandler):
    received: list[dict] = []
    status = 201

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Pipeline.received.append({"auth": self.headers.get("Authorization"), "body": body})
        self.send_response(Pipeline.status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        ok = Pipeline.status < 300
        self.wfile.write(json.dumps({"ok": ok, "id": "idea-20260919-abc" if ok else None, "status": "received"}).encode())

    def log_message(self, *_args):
        pass


def serve():
    Pipeline.received = []
    Pipeline.status = 201
    server = HTTPServer(("127.0.0.1", 0), Pipeline)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def worker_for(tmp_path: Path, bridge: FakeBridge, triage: FakeTriage, clock=None) -> WhatsAppIntakeWorker:
    worker = WhatsAppIntakeWorker(
        settings(tmp_path / "data", tmp_path / "Projects"),
        bridge=bridge,  # type: ignore[arg-type]
        triage=triage,  # type: ignore[arg-type]
        transcribe=lambda _path, _mime: "En el audio dice que es una pizzería con delivery.",
    )
    return worker


def test_without_config_the_regular_flow_is_untouched(tmp_path: Path) -> None:
    (tmp_path / "Projects" / "ideas-proyectos").mkdir(parents=True)
    write_record(tmp_path / "data", project="ideas-proyectos", message_id="m1", kind="text", text="hola")
    triage = FakeTriage(decision(actionable=False))
    assert worker_for(tmp_path, FakeBridge(), triage).run_once() == 1
    assert len(triage.calls) == 1


def test_ideas_batch_goes_to_the_pipeline_without_triage_or_chat(tmp_path: Path) -> None:
    server = serve()
    token = tmp_path / "token"
    token.write_text("secret-123\n")
    ideas_project(tmp_path / "Projects", {"version": 1, "enabled": True, "url": f"http://127.0.0.1:{server.server_port}/ideas", "token_file": str(token)})
    text = write_record(tmp_path / "data", project="ideas-proyectos", message_id="m1", kind="text",
                        text="Mirá https://www.instagram.com/pizzeriahalloween/")
    audio = write_record(tmp_path / "data", project="ideas-proyectos", message_id="m2", kind="audio")
    bridge, triage = FakeBridge(), FakeTriage(decision(actionable=True))
    worker = worker_for(tmp_path, bridge, triage)

    assert worker.run_once() == 2
    assert triage.calls == [] and bridge.created == [] and bridge.standard_created == []
    assert len(Pipeline.received) == 1
    sent = Pipeline.received[0]
    assert sent["auth"] == "Bearer secret-123"
    assert sent["body"]["schema"] == "nienfos.ideas-forward/1"
    assert [m["message_id"] for m in sent["body"]["messages"]] == ["m1", "m2"]
    assert "pizzeriahalloween" in sent["body"]["messages"][0]["text"]
    assert "pizzería con delivery" in sent["body"]["messages"][1]["text"]  # local transcript travels
    marker = json.loads((text / SUBMISSION_FILENAME).read_text())
    assert marker["mode"] == "ideas_forward" and marker["idea_id"] == "idea-20260919-abc"
    assert (audio / SUBMISSION_FILENAME).exists()
    assert not (text / TRIAGE_FILENAME).exists()

    assert worker.run_once() == 0  # delivered once
    assert len(Pipeline.received) == 1
    server.shutdown()


def test_rejected_post_keeps_records_pending_and_waits_before_retrying(tmp_path: Path) -> None:
    server = serve()
    Pipeline.status = 503
    token = tmp_path / "token"
    token.write_text("t")
    ideas_project(tmp_path / "Projects", {"version": 1, "enabled": True, "url": f"http://127.0.0.1:{server.server_port}/ideas", "token_file": str(token)})
    record = write_record(tmp_path / "data", project="ideas-proyectos", message_id="m1", kind="text", text="https://instagram.com/x")
    worker = worker_for(tmp_path, FakeBridge(), FakeTriage(decision(actionable=True)))

    worker.run_once()
    assert not (record / SUBMISSION_FILENAME).exists()
    assert (record / ATTEMPT_FILENAME).exists()
    worker.run_once()
    assert len(Pipeline.received) == 1, "no hammering inside the retry window"
    server.shutdown()


def test_dry_run_writes_the_payload_without_network(tmp_path: Path) -> None:
    ideas_project(tmp_path / "Projects", {"version": 1, "enabled": True, "dry_run": True})
    record = write_record(tmp_path / "data", project="ideas-proyectos", message_id="m1", kind="text", text="https://instagram.com/x")
    assert worker_for(tmp_path, FakeBridge(), FakeTriage(decision(actionable=True))).run_once() == 1
    outbox = list((tmp_path / "data" / "ideas-forward" / "outbox").glob("*.json"))
    assert len(outbox) == 1
    assert json.loads(outbox[0].read_text())["messages"][0]["text"] == "https://instagram.com/x"
    assert json.loads((record / SUBMISSION_FILENAME).read_text())["dry_run"] is True


def test_config_refuses_plain_http_across_the_network(tmp_path: Path) -> None:
    workspace = ideas_project(tmp_path, {"version": 1, "enabled": True, "url": "http://100.92.64.118:8796/ideas"})
    assert ideas_config(workspace) is None
    (workspace / CONFIG_RELATIVE).write_text(json.dumps({"version": 1, "enabled": False, "url": "https://x.ts.net/ideas"}))
    assert ideas_config(workspace) is None
