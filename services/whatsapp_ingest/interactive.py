"""Local interactive intake adapter. Only explicitly enabled requests are processed."""

from __future__ import annotations
import sqlite3
import time
from pathlib import Path


def tick(worker):
    from services.whatsapp_ingest.worker import (
        atomic_write_json,
        read_json,
        resolve_project_directive,
        discover_projects,
        SUBMISSION_FILENAME,
    )

    root = worker.settings.data_dir / "interactive"
    config = read_json(root / "config.json")
    if not isinstance(config, dict) or not config.get("enabled"):
        return
    root.mkdir(parents=True, exist_ok=True)
    catalog = root / "catalog.json"
    if not catalog.exists() or time.time() - catalog.stat().st_mtime > 30:
        projects = worker.bridge._request("/workspaces")
        latest = {}
        for filename in config.get("databases", []):
            db = Path(filename).resolve()
            with sqlite3.connect(
                db.as_uri() + "?mode=ro", uri=True, timeout=3
            ) as connection:
                for path, stamp in connection.execute("""
                    SELECT s.workspace_path, MAX(COALESCE(j.completed_at,j.updated_at,j.created_at))
                    FROM jobs j JOIN sessions s ON s.id=j.session_id
                    WHERE j.status != 'pending' GROUP BY s.workspace_path
                """):
                    latest[path] = max(latest.get(path, ""), stamp or "")
        aliases = {
            p["slug"]: p["identifiers"]
            for p in discover_projects(worker.settings.projects_root)
        }
        entries = []
        for p in projects:
            path = Path(p["path"]).resolve()
            if path.parent == worker.settings.projects_root and path.is_dir():
                entries.append(
                    {
                        "slug": path.name,
                        "name": p["name"],
                        "last_execution_at": latest.get(str(path)),
                        "aliases": aliases.get(path.name, []),
                    }
                )
        entries.sort(key=lambda p: (p["name"].casefold(), p["slug"]))
        entries.sort(key=lambda p: p["last_execution_at"] or "", reverse=True)
        atomic_write_json(
            catalog, {"version": 1, "updated_at": time.time(), "projects": entries}
        )
    requests = root / "requests"
    requests.mkdir(exist_ok=True)
    for file in sorted(requests.glob("*.json")):
        state = read_json(file)
        if not isinstance(state, dict) or state.get("status") not in {
            "queued",
            "running",
        }:
            continue
        try:
            client = worker.direct_cli_bridge if state.get("cli") else worker.bridge
            if state["status"] == "queued":
                project = str(state["project"])
                resolution = resolve_project_directive(
                    project, worker.settings.projects_root
                )
                if (
                    resolution.get("status") != "matched"
                    or resolution.get("project") != project
                ):
                    raise ValueError("Invalid selected workspace")
                if state.get("channel") == "backlog":
                    enqueue_backlog(worker, state, file, resolution)
                    continue
                records = []
                for relative in state["records"]:
                    source = (worker.settings.data_dir / relative).resolve()
                    if not source.is_relative_to(
                        (worker.settings.data_dir / "inbox").resolve()
                    ):
                        raise ValueError("Invalid record path")
                    manifest = read_json(source / "message.json")
                    # A restart may find records already moved; discover by stable message ID.
                    if not isinstance(manifest, dict):
                        candidates = list(
                            (worker.settings.data_dir / "inbox" / project).glob(
                                f"*/{source.name}/message.json"
                            )
                        )
                        if len(candidates) != 1:
                            raise ValueError("Original record missing")
                        source = candidates[0].parent
                        manifest = read_json(candidates[0])
                    manifest["interactive_request_id"] = state["id"]
                    atomic_write_json(source / "message.json", manifest)
                    if source.parent.parent.name != project:
                        source, manifest = worker._move_direct_record(
                            source,
                            manifest,
                            project,
                            {
                                **resolution,
                                "direct_batch_id": state["id"],
                                "delivery_mode": "direct_cli"
                                if state.get("cli")
                                else "triage",
                                "response_channel": state["channel"],
                            },
                        )
                    if state.get("session_id"):
                        atomic_write_json(
                            source / "channel-session.json",
                            {
                                "session_id": state["session_id"],
                                "response_channel": state["channel"],
                            },
                        )
                    # The normal worker must not see partial selection state.
                    (source / "READY").touch(mode=0o600, exist_ok=True)
                    record = worker._prepare_record(source)
                    if record is not None:
                        records.append(record)
                if not records:
                    raise ValueError("Empty request")
                submissions = [read_json(r.path / SUBMISSION_FILENAME) for r in records]
                existing = [
                    s for s in submissions if isinstance(s, dict) and s.get("job_id")
                ]
                if existing:
                    submission = existing[0]
                else:
                    # Reserve before HTTP send: an uncertain job is never silently duplicated.
                    state["status"] = "submitting"
                    atomic_write_json(file, state)
                    worker._process_channel_batch(records)
                    submission = read_json(records[0].path / SUBMISSION_FILENAME)
                state.update(
                    status="running",
                    session_id=submission["session_id"],
                    job_id=submission["job_id"],
                    submitted_at=time.time(),
                )
                atomic_write_json(file, state)
            result = client.get_job(state["job_id"])
            if result.get("status") in {"completed", "failed", "cancelled"}:
                state.update(
                    status="finished",
                    result_status=result["status"],
                    finished_at=time.time(),
                )
                state["reply"] = (
                    str(
                        result.get("response")
                        or "El trabajo terminó sin una respuesta de texto."
                    )
                    if result["status"] == "completed"
                    else "El pedido no pudo completarse. Podés ver el detalle en Codex Bridge."
                )
                atomic_write_json(file, state)
        except Exception as error:
            state["last_error"] = type(error).__name__
            atomic_write_json(file, state)


def enqueue_backlog(worker, state, file, resolution):
    from services.whatsapp_ingest.worker import (
        read_json,
        atomic_write_json,
        build_direct_cli_message,
    )

    records = []
    for relative in state["records"]:
        source = (worker.settings.data_dir / relative).resolve()
        if not source.is_relative_to((worker.settings.data_dir / "inbox").resolve()):
            raise ValueError("Invalid backlog record")
        manifest = read_json(source / "message.json")
        if not isinstance(manifest, dict):
            raise ValueError("Original backlog record missing")
        manifest["project"] = state["project"]
        manifest["delivery_mode"] = "backlog"
        atomic_write_json(source / "message.json", manifest)
        # This worker is serial: never leave READY for the ordinary intake pass.
        marker = source / "READY"
        marker.touch(mode=0o600)
        try:
            record = worker._prepare_record(source)
            if record is None:
                raise ValueError("Backlog record could not be prepared")
            records.append(record)
        finally:
            marker.unlink(missing_ok=True)
    if not records:
        raise ValueError("Empty backlog request")
    text = (
        build_direct_cli_message(records)
        or "Revisar el material adjunto y atender el pedido registrado."
    )
    images = [str(r.media_path) for r in records if r.kind == "image" and r.media_path]
    references = [
        str(r.media_path) for r in records if r.kind != "image" and r.media_path
    ]
    result = worker.bridge._request(
        "/work/backlog",
        method="POST",
        payload={
            "workspace_path": str(records[0].workspace),
            "source": "whatsapp",
            "source_key": state["id"],
            "title": text[:120],
            "instruction": text,
            "attachments": images,
            "references": references,
        },
    )
    state.update(
        status="finished",
        result_status="queued",
        backlog_id=result["id"],
        reply=f"Guardado en el backlog de {state['project']}. Se ejecutará al completar el trabajo anterior. Referencia: {result['id']}.",
    )
    atomic_write_json(file, state)
