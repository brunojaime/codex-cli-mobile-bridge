from __future__ import annotations

import json
import os
from pathlib import Path

from backend.app.infrastructure.transcription.base import AudioTranscriptionError
from services.whatsapp_ingest.worker import (
    NO_SPEECH_TRANSCRIPT,
    PLANNER_PROFILE_COLOR,
    PLANNER_PROFILE_ID,
    SUBMISSION_FILENAME,
    TRANSCRIPT_FILENAME,
    TRIAGE_FILENAME,
    TriageDecision,
    WhatsAppIntakeWorker,
    WorkerSettings,
)


def decision(*, actionable: bool) -> TriageDecision:
    return TriageDecision(
        value={
            "version": 1,
            "actionable": actionable,
            "classification": "implementation_request" if actionable else "social",
            "confidence": "high",
            "task_title": "Cambiar el botón" if actionable else "",
            "summary": "El cliente pidió cambiar el botón." if actionable else "Agradecimiento.",
            "requested_outcome": "Actualizar el botón principal." if actionable else "",
            "rationale": "Requiere trabajo." if actionable else "No requiere trabajo.",
            "source_message_ids": ["text-1", "audio-1"] if actionable else ["text-1"],
            "needs_clarification": False,
            "clarification_question": "",
        }
    )


class FakeTriage:
    def __init__(self, result: TriageDecision) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    def decide(
        self,
        *,
        workspace_path: Path,
        records,
        recent_context: list[dict[str, object]],
    ) -> TriageDecision:
        self.calls.append(
            {
                "workspace_path": workspace_path,
                "records": records,
                "recent_context": recent_context,
            }
        )
        return self.result


class FakeBridge:
    def __init__(self) -> None:
        self.created: list[dict[str, object]] = []
        self.submitted: list[dict[str, object]] = []

    def create_planning_session(self, *, title: str, workspace_path: Path) -> str:
        self.created.append(
            {
                "title": title,
                "workspace_path": workspace_path,
                "profile_id": PLANNER_PROFILE_ID,
                "profile_color": PLANNER_PROFILE_COLOR,
            }
        )
        return "session-1"

    def submit_planning(
        self,
        *,
        session_id: str,
        workspace_path: Path,
        prompt: str,
    ) -> dict[str, object]:
        self.submitted.append(
            {
                "session_id": session_id,
                "workspace_path": workspace_path,
                "prompt": prompt,
            }
        )
        return {"job_id": "job-1", "session_id": session_id}


def write_record(
    data_dir: Path,
    *,
    project: str,
    message_id: str,
    kind: str,
    text: str | None = None,
    ready_mtime: float | None = None,
) -> Path:
    record = data_dir / "inbox" / project / "2026-09-19" / message_id
    record.mkdir(parents=True)
    manifest = {
        "message_id": message_id,
        "group_id": "group-1@g.us",
        "group_subject": "Cliente Uno",
        "participant_id": "5491111111111@s.whatsapp.net",
        "push_name": "Cliente",
        "kind": kind,
        "text": text if kind == "text" else None,
        "mime_type": "audio/ogg",
        "media_file": "audio-original.ogg" if kind == "audio" else None,
        "whatsapp_timestamp": "2026-09-19T12:00:00+00:00",
    }
    (record / "message.json").write_text(json.dumps(manifest), encoding="utf-8")
    if kind == "audio":
        (record / "audio-original.ogg").write_bytes(b"fake-audio")
    ready = record / "READY"
    ready.write_text("", encoding="utf-8")
    if ready_mtime is not None:
        os.utime(ready, (ready_mtime, ready_mtime))
    return record


def settings(data_dir: Path, projects_root: Path, **overrides) -> WorkerSettings:
    return WorkerSettings(
        data_dir=data_dir,
        projects_root=projects_root,
        settle_seconds=overrides.pop("settle_seconds", 0),
        **overrides,
    )


def test_actionable_batch_opens_new_colored_planning_chat(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    projects_root = tmp_path / "Projects"
    workspace = projects_root / "cliente-uno"
    workspace.mkdir(parents=True)
    text_record = write_record(
        data_dir,
        project="cliente-uno",
        message_id="text-1",
        kind="text",
        text="Cambiar el color del botón",
    )
    audio_record = write_record(
        data_dir,
        project="cliente-uno",
        message_id="audio-1",
        kind="audio",
    )
    bridge = FakeBridge()
    triage = FakeTriage(decision(actionable=True))
    worker = WhatsAppIntakeWorker(
        settings(data_dir, projects_root),
        bridge=bridge,  # type: ignore[arg-type]
        triage=triage,  # type: ignore[arg-type]
        transcribe=lambda _path, _mime: "El audio pide agregar un filtro.",
    )

    assert worker.run_once() == 2
    assert len(triage.calls) == 1
    assert len(bridge.created) == 1
    assert bridge.created[0]["profile_id"] == PLANNER_PROFILE_ID
    assert bridge.created[0]["profile_color"] == PLANNER_PROFILE_COLOR
    assert bridge.created[0]["title"] == "WhatsApp · Cambiar el botón"
    assert len(bridge.submitted) == 1
    planning_prompt = str(bridge.submitted[0]["prompt"])
    assert "No implementes todavía" in planning_prompt
    assert "Cambiar el color del botón" in planning_prompt
    assert "agregar un filtro" in planning_prompt
    assert (audio_record / TRANSCRIPT_FILENAME).read_text().strip() == (
        "El audio pide agregar un filtro."
    )
    assert (text_record / TRIAGE_FILENAME).exists()
    submission = json.loads((text_record / SUBMISSION_FILENAME).read_text())
    assert submission["status"] == "planning_submitted"
    assert submission["job_id"] == "job-1"

    assert worker.run_once() == 0
    assert len(bridge.submitted) == 1


def test_non_actionable_batch_is_archived_without_visible_chat(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    projects_root = tmp_path / "Projects"
    (projects_root / "cliente-uno").mkdir(parents=True)
    record = write_record(
        data_dir,
        project="cliente-uno",
        message_id="text-1",
        kind="text",
        text="Gracias, buenísimo",
    )
    bridge = FakeBridge()
    triage = FakeTriage(decision(actionable=False))
    worker = WhatsAppIntakeWorker(
        settings(data_dir, projects_root),
        bridge=bridge,  # type: ignore[arg-type]
        triage=triage,  # type: ignore[arg-type]
    )

    assert worker.run_once() == 1
    assert len(triage.calls) == 1
    assert bridge.created == []
    assert bridge.submitted == []
    submission = json.loads((record / SUBMISSION_FILENAME).read_text())
    assert submission["status"] == "triaged_no_action"
    assert submission["session_id"] is None


def test_waits_for_quiet_window_after_latest_message(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    projects_root = tmp_path / "Projects"
    (projects_root / "cliente-uno").mkdir(parents=True)
    write_record(
        data_dir,
        project="cliente-uno",
        message_id="text-1",
        kind="text",
        text="Primera parte",
        ready_mtime=10,
    )
    write_record(
        data_dir,
        project="cliente-uno",
        message_id="text-2",
        kind="text",
        text="Segunda parte",
        ready_mtime=95,
    )
    now = [100.0]
    triage = FakeTriage(decision(actionable=False))
    worker = WhatsAppIntakeWorker(
        settings(data_dir, projects_root, settle_seconds=10),
        bridge=FakeBridge(),  # type: ignore[arg-type]
        triage=triage,  # type: ignore[arg-type]
        clock=lambda: now[0],
    )

    assert worker.run_once() == 0
    assert triage.calls == []
    now[0] = 106
    assert worker.run_once() == 2
    assert len(triage.calls) == 1


def test_leaves_provisional_project_records_for_later_promotion(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    projects_root = tmp_path / "Projects"
    record = write_record(
        data_dir,
        project="pending-cliente-abc123",
        message_id="text-1",
        kind="text",
        text="Pedido",
    )
    bridge = FakeBridge()
    triage = FakeTriage(decision(actionable=True))
    worker = WhatsAppIntakeWorker(
        settings(data_dir, projects_root),
        bridge=bridge,  # type: ignore[arg-type]
        triage=triage,  # type: ignore[arg-type]
    )

    assert worker.run_once() == 0
    assert not (record / SUBMISSION_FILENAME).exists()
    assert triage.calls == []
    assert bridge.created == []


def test_audio_without_speech_is_archived_without_llm_or_retry(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    projects_root = tmp_path / "Projects"
    (projects_root / "cliente-uno").mkdir(parents=True)
    record = write_record(
        data_dir,
        project="cliente-uno",
        message_id="silent-audio",
        kind="audio",
    )
    bridge = FakeBridge()
    triage = FakeTriage(decision(actionable=True))

    def no_speech(_path: Path, _mime: str | None) -> str:
        raise AudioTranscriptionError("Local faster-whisper returned an empty transcript.")

    worker = WhatsAppIntakeWorker(
        settings(data_dir, projects_root),
        bridge=bridge,  # type: ignore[arg-type]
        triage=triage,  # type: ignore[arg-type]
        transcribe=no_speech,
    )

    assert worker.run_once() == 1
    assert (record / TRANSCRIPT_FILENAME).read_text().strip() == NO_SPEECH_TRANSCRIPT
    assert json.loads((record / SUBMISSION_FILENAME).read_text())["status"] == (
        "triaged_no_action"
    )
    assert triage.calls == []
    assert bridge.created == []
    assert worker.run_once() == 0
