"""Relevo entre equipos: botón «Pasar a Batata» de la app.

El backend sólo lanza `scripts/relevo.py ir <destino> --todo` desacoplado (nueva sesión de
proceso) y expone su estado. Una sola ejecución a la vez: si hay una en curso se devuelve esa.
El script cierra ordenadamente todos los chats activos (incluido el del propio Bridge que lo
lanzó), así que no puede depender de ningún job del Bridge para sobrevivir.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "relevo.py"
_lock = threading.Lock()

router = APIRouter(prefix="/relevo", tags=["relevo"])


def runs_dir() -> Path:
    path = Path(os.environ.get("RELEVO_RUNS_DIR", Path.home() / ".local/state/relevo/runs"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def hosts_file() -> Path:
    return Path(os.environ.get("RELEVO_HOSTS_FILE", REPO_ROOT / "config" / "relevo-hosts.json"))


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:  # un proceso zombie (terminado sin recolectar) no cuenta como vivo
        return Path(f"/proc/{pid}/stat").read_text().split()[2] != "Z"
    except OSError:
        return True


def _run_view(meta: dict[str, Any]) -> dict[str, Any]:
    folder = runs_dir() / meta["id"]
    log_lines = []
    log_path = folder / "progress.log"
    if log_path.exists():
        log_lines = [line for line in log_path.read_text(errors="ignore").splitlines() if line.strip()]
    result = None
    result_path = folder / "result.json"
    if result_path.exists() and result_path.stat().st_size:
        try:
            result = json.loads(result_path.read_text())
        except ValueError:
            result = None
    exit_path = folder / "exit_code"
    exit_code = int(exit_path.read_text()) if exit_path.exists() else None
    if exit_code is None and _alive(int(meta["pid"])):
        status = "running"
    elif exit_code == 0 and result is not None:
        status = "finished"
    else:
        status = "failed"
    projects = (result or {}).get("proyectos", [])
    return {
        **meta,
        "status": status,
        "exit_code": exit_code,
        "progress": log_lines[-12:],
        "projects": projects,
        "error": None if status != "failed" else (log_lines[-1] if log_lines else "El relevo terminó sin resultado"),
    }


def _latest() -> dict[str, Any] | None:
    metas = []
    for meta_path in runs_dir().glob("*/meta.json"):
        try:
            metas.append(json.loads(meta_path.read_text()))
        except ValueError:
            continue
    return max(metas, key=lambda m: m["started_at"]) if metas else None


class RelevoStartRequest(BaseModel):
    destination: str = Field(..., min_length=1, max_length=40, pattern=r"^[a-z0-9-]+$")


@router.get("/destinations")
def destinations() -> dict[str, Any]:
    try:
        hosts = json.loads(hosts_file().read_text())["hosts"]
    except (OSError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=503, detail=f"Configuración de equipos no disponible: {exc}") from exc
    import socket

    me = socket.gethostname().lower()
    items = []
    for name, cfg in hosts.items():
        is_self = any(me == h.lower() for h in cfg.get("match_hostnames", []))
        enabled = cfg.get("enabled", True) is not False and bool(cfg.get("bridges"))
        if not is_self:
            items.append({"name": name, "enabled": enabled, "note": cfg.get("note")})
    return {"destinations": items}


@router.post("/runs", status_code=202)
def start_run(payload: RelevoStartRequest) -> dict[str, Any]:
    with _lock:
        latest = _latest()
        if latest is not None:
            view = _run_view(latest)
            if view["status"] == "running":
                return {**view, "already_running": True}
        names = {d["name"] for d in destinations()["destinations"] if d["enabled"]}
        if payload.destination not in names:
            raise HTTPException(status_code=400, detail=f"Destino no habilitado: {payload.destination}")
        run_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        folder = runs_dir() / run_id
        folder.mkdir(parents=True)
        # Un shell mínimo deja constancia del código de salida aunque el backend se reinicie.
        command = (
            f'"{sys.executable}" "{SCRIPT}" ir "{payload.destination}" --todo '
            f'> "{folder}/result.json" 2> "{folder}/progress.log"; echo $? > "{folder}/exit_code"'
        )
        process = subprocess.Popen(
            ["/bin/sh", "-c", command],
            cwd=str(REPO_ROOT),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        threading.Thread(target=process.wait, daemon=True).start()  # evita procesos zombie
        meta = {"id": run_id, "destination": payload.destination, "pid": process.pid,
                "started_at": time.time()}
        (folder / "meta.json").write_text(json.dumps(meta))
        return {**_run_view(meta), "already_running": False}


@router.get("/runs/latest")
def latest_run() -> dict[str, Any]:
    latest = _latest()
    if latest is None:
        return {"status": "none"}
    return _run_view(latest)


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    meta_path = runs_dir() / Path(run_id).name / "meta.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Relevo no encontrado")
    return _run_view(json.loads(meta_path.read_text()))
