"""Complete the authorized laboratory setup when deferred backend activation is ready."""

from __future__ import annotations
import argparse
from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(".tmp")
    pending.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    pending.replace(path)


def render(folder, lab, state):
    backend = (
        json.loads((folder / "estado.json").read_text())
        if (folder / "estado.json").exists()
        else {}
    )
    names = {
        "waiting_for_idle": "Esperando el cierre de las corridas",
        "active": "Activo",
        "waiting_for_backend_connection": "Esperando conexión",
        "prepared_waiting_for_idle": "Preparado",
    }
    rows = "".join(
        "<li><strong>"
        + html.escape(k.upper())
        + ":</strong> "
        + html.escape(names.get(v.get("state", ""), v.get("state", "")))
        + "</li>"
        for k, v in backend.items()
    )
    content = (
        """<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Backlog y Tu noche · Despliegue</title><style>body{font:16px/1.6 system-ui;background:#f2f7f5;color:#153d30;max-width:760px;margin:auto;padding:22px}h1{font-size:30px;line-height:1.15}h2{font-size:21px}section{padding:20px;border:1px solid #d8e7df;background:white;border-radius:20px;margin:20px 0}a{color:#006c52}img{display:block;width:100%;max-width:390px;margin:14px auto;border:1px solid #d8e7df;border-radius:18px}li{margin:8px 0}.poll{background:#effbf4;padding:18px;border-radius:16px}.choice{border:1px solid #a4cbb8;padding:12px;margin:10px 0;border-radius:12px}small{color:#527365}</style><main><h1>Backlog y Tu noche</h1><p>Actualización 1.0.0+157 · Datos reales · Sin activar cambios en los productos QA o producción.</p><section><h2>Backend</h2><ul>"""
        + rows
        + '''</ul><p>El activador espera que terminen los jobs y mensajes aceptados. No corta esta conversación para reiniciar.</p><a href="estado.json">Ver estado actualizado del activador</a></section><section><h2>App y web</h2><p>La web ya tiene la versión 157. Los APK normal y DEV 1.0.0+157 ya están publicados por GitHub Actions. Volvé a abrir la app y aceptá la actualización del canal que ya tenés instalado.</p><p><a href="https://github.com/brunojaime/codex-cli-mobile-bridge/releases/tag/android-v1.0.0-build.157">Release Android normal</a><br><a href="https://github.com/brunojaime/codex-cli-mobile-bridge/releases/tag/android-dev-v1.0.0-build.157">Release Android DEV</a><br><a href="https://batata-default-string.tail0302c4.ts.net/app/">Abrir Bridge web dentro de Tailscale</a></p><p>En la app: menú ⋮ → <strong>Backlog y Tu noche</strong>. Para cargar desde el chat: <code>/backlog</code> seguido del pedido.</p></section><section><h2>Así queda WhatsApp</h2><p>Después de elegir proyecto:</p><div class="poll"><strong>¿Cómo querés continuar?</strong><div class="choice">○ WhatsApp · Charlar</div><div class="choice">○ Bridge · Ejecutar</div><div class="choice">◉ Backlog · Ejecutar después</div><small>El comprobante se envía después de guardar el encargo.</small></div><p>La opción Backlog guarda en el mismo coordinador que la app y Feedback. Codex Folder no dispara tareas.</p></section><section><h2>Así se ve Tu noche</h2><p>Capturas del widget implementado con un ejemplo sintético. Los avances reales aparecerán después de las ejecuciones.</p><a href="../work-coordinator-pilot/tu-noche.png"><img src="../work-coordinator-pilot/tu-noche.png" alt="Tu noche: avances, bloqueos y decisiones"></a><a href="../work-coordinator-pilot/decisiones.png"><img src="../work-coordinator-pilot/decisiones.png" alt="Elegir una recomendación, guardar observaciones o rechazar"></a></section><section><h2>Primera prueba con agentes reales</h2><p>Laboratorio aislado: <strong>codex-night-lab-20261105</strong>.</p><ol><li>Cambiar el título de la página.</li><li>Agregar una descripción conservando el título anterior.</li></ol><p>Ambos encargos exigen validación, commit, push a GitHub y DEV comprobado. No modifican datos de clientes.</p><p><a href="'''
        + html.escape(lab["preview_url"])
        + """/">Abrir DEV del laboratorio dentro de Tailscale</a></p><p><strong>Estado del laboratorio:</strong> """
        + html.escape(state.get("state", "Esperando activación"))
        + """</p><a href="laboratorio.json">Ver comprobantes del laboratorio</a></section><section><h2>Alcance de esta activación</h2><p>El piloto nocturno queda limitado al laboratorio: 22:30–08:00 Argentina, hasta tres encargos por ventana y una observación autónoma por noche. Peluquería y Cebando Tradición todavía requieren adaptar su procedimiento DEV real antes de habilitarlos.</p><p>La bandeja se actualiza al abrir la app. El push de preguntas nocturnas con la app cerrada sigue pendiente. Los SDK de Feedback tienen cambios fuente; esta activación no actualiza automáticamente cada aplicación consumidora.</p></section></main></html>"""
    )
    pending = folder / "index.tmp"
    pending.write_text(content)
    pending.replace(folder / "index.html")


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    args = parser.parse_args()
    lab = json.loads(args.lab.read_text())
    folder = args.report_dir
    state = {
        "state": "Esperando la activación del coordinador DEV",
        "real_agents": True,
        "tasks": [],
    }
    policy = {
        "workspace_path": lab["workspace"],
        "enabled": True,
        "dev_branch": "dev/lab",
        "remote": "origin",
        "dev_url": "http://127.0.0.1:8290/version.json",
        "preview_url": lab["preview_url"] + "/",
        "validate": [["python3", "validate.py"]],
        "deploy": ["python3", "deploy_dev.py", lab["published"]],
        "dev_isolated": True,
        "reconcile_dev": True,
        "generator_turns": 2,
        "reviewer_turns": 2,
        "max_tasks_per_day": 3,
        "max_observations_per_night": 1,
        "task_timeout_minutes": 30,
        "command_timeout_seconds": 120,
        "autonomous": True,
        "focus": "Mejorar exclusivamente la claridad y accesibilidad del HTML de este laboratorio, conservando el propósito de prueba y sin agregar dependencias, cuentas, integraciones ni funciones de negocio.",
    }
    instructions = [
        (
            "Título del laboratorio",
            "En index.html cambiar el h1 y el title a «Mi noche sigue avanzando». Conservar el resto del contenido. Validar con python3 validate.py y dejar un commit. El coordinador se encarga del push y DEV.",
        ),
        (
            "Descripción después del título",
            "Revisar el resultado del encargo anterior y conservar su título. En index.html agregar un párrafo breve: «Mientras descansás, el backlog continúa en orden». Validar con python3 validate.py y dejar un commit. El coordinador se encarga del push y DEV.",
        ),
    ]
    submitted = False
    with httpx.Client(
        base_url="http://127.0.0.1:8118", timeout=90, trust_env=False
    ) as client:
        while True:
            try:
                schema = client.get("/openapi.json").raise_for_status().json()
                properties = (
                    schema.get("components", {})
                    .get("schemas", {})
                    .get("WorkPolicy", {})
                    .get("properties", {})
                )
                if "preview_url" not in properties:
                    raise ValueError("Coordinator not yet activated")
                if not submitted:
                    client.put("/work/policy", json=policy).raise_for_status()
                    tasks = []
                    for index, (title, instruction) in enumerate(instructions):
                        response = client.post(
                            "/work/backlog",
                            json={
                                "workspace_path": lab["workspace"],
                                "source": "chat",
                                "source_key": f"deploy-pilot-157-{index}",
                                "title": title,
                                "instruction": instruction,
                            },
                        ).raise_for_status()
                        tasks.append(response.json()["id"])
                    state.update(
                        state="Dos encargos autorizados guardados en la cola",
                        tasks=tasks,
                        night_enabled=True,
                    )
                    submitted = True
                overview = client.get("/work").raise_for_status().json()
                project = next(
                    p
                    for p in overview["projects"]
                    if p["workspace_path"] == lab["workspace"]
                )
                tasks = (
                    project.get("completed", [])
                    + project.get("queue", [])
                    + ([project["active"]] if project.get("active") else [])
                )
                relevant = [
                    {
                        "id": t["id"],
                        "title": t["title"],
                        "status": t["status"],
                        "receipt": t.get("receipt"),
                        "problem": t.get("problem"),
                    }
                    for t in tasks
                    if t["id"] in state["tasks"]
                ]
                state["results"] = relevant
                if len(relevant) == 2 and all(
                    t["status"] == "completed" for t in relevant
                ):
                    state["state"] = (
                        "Prueba real completada: ambos commits en GitHub y DEV comprobado"
                    )
                elif any(t["status"] in {"blocked", "uncertain"} for t in relevant):
                    state["state"] = (
                        "La prueba requiere atención; consultar el problema visible"
                    )
                state["updated_at"] = datetime.now(timezone.utc).isoformat()
            except (httpx.HTTPError, ValueError, StopIteration) as exc:
                state["last_check"] = type(exc).__name__
            write(folder / "laboratorio.json", state)
            render(folder, lab, state)
            time.sleep(15)  # Polling deterministic status; never a model call.


if __name__ == "__main__":
    main()
