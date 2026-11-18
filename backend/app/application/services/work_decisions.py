"""Escalate terminal recovery blocks into the existing durable decision inbox.

Notices are coordinator messages, never model runs. Their normal message SQL
trigger uses the existing opted-in push transport; no second sender or queue.
"""

from __future__ import annotations

import hashlib
import json
from uuid import NAMESPACE_URL, uuid5

from .work_coordinator import WorkConflict


def migrate(db):
    columns = {r[1] for r in db.execute("PRAGMA table_info(work_questions)")}
    for name, definition in {
        "source_task_id": "TEXT",
        "source_revision": "INTEGER",
        "source_signature": "TEXT",
        "notice_sent": "INTEGER NOT NULL DEFAULT 0",
    }.items():
        if name not in columns:
            db.execute(f"ALTER TABLE work_questions ADD COLUMN {name} {definition}")
    db.commit()


def signature(task):
    # Detect intervening retries, operator actions and changed failure evidence.
    return hashlib.sha256(
        json.dumps(
            [
                task["revision"],
                task["status"],
                task["problem"],
                task["failure"],
                task["stop_requested"],
            ],
            sort_keys=True,
        ).encode()
    ).hexdigest()


LABELS = {
    "credentials_required": "Revisar credenciales",
    "operator_setup_required": "Configurar adaptador",
    "publication_needs_reconciliation": "Comprobar publicación",
    "publication_uncertain": "Comprobar publicación incierta",
    "repeated_failure": "Revisar fallo repetido",
    "attempts_exhausted": "Revisar límite de reintentos",
    "agent_cycle_needs_review": "Revisar ciclo fallido",
    "diagnosis_required": "Comprobar estado",
}


REASONS = {
    "credentials_required": "El operador necesita acceso a credenciales. Revisar la configuración en Secrets antes de comprobar nuevamente.",
    "operator_setup_required": "El adaptador de validación o publicación necesita completar su configuración.",
    "publication_needs_reconciliation": "Hay que comprobar qué versión quedó realmente publicada antes de reintentar.",
    "diagnosis_required": "Hace falta comprobar el estado del trabajo y de DEV antes de continuar.",
    "repeated_failure": "La misma validación volvió a fallar; se detuvieron los reintentos automáticos.",
    "attempts_exhausted": "Se alcanzó el límite de recuperaciones automáticas de esta tarea.",
    "agent_cycle_needs_review": "El ciclo terminó con fallos y necesita revisión.",
    "publication_uncertain": "La publicación tiene un resultado incierto; no se repetirá a ciegas.",
}


def reconcile(service, db):
    from .work_recovery import recovery_decision

    # Questions also surface outside the nightly admission window and its budgets.
    for q in db.execute(
        "SELECT * FROM work_questions WHERE source_task_id IS NOT NULL AND selected IS NULL"
    ).fetchall():
        task = db.execute(
            "SELECT * FROM work_tasks WHERE id=?", (q["source_task_id"],)
        ).fetchone()
        if not task or signature(task) != q["source_signature"]:
            db.execute("UPDATE work_questions SET selected=-2 WHERE id=?", (q["id"],))
            cancel_notice(service, q["id"])
    for task in db.execute(
        "SELECT * FROM work_tasks WHERE status='blocked' AND stop_requested=0"
    ).fetchall():
        if not task["policy"]:
            continue
        policy = json.loads(task["policy"])
        if not policy.get("enabled"):
            continue
        state = task["recovery_state"]
        if state not in REASONS:
            state = recovery_decision(
                json.loads(task["failure"]) if task["failure"] else None,
                recoveries=task["recoveries"],
                limit=policy.get("max_recoveries_per_task", 3),
                stopped=False,
            )
        # An old generic block is still eligible for its first automatic diagnosis.
        if state == "diagnosis_required" and (task["problem"] or "").startswith(
            "Falló una operación de validación/DEV ("
        ):
            continue
        if state not in REASONS:
            continue
        request = json.loads(task["payload"])
        sig = signature(task)
        qid = str(uuid5(NAMESPACE_URL, "work-block:" + task["id"] + ":" + sig))
        options = [
            {
                "label": "Comprobar nuevamente sin publicar",
                "instruction": REASONS[state],
                "action": "diagnose",
            },
            {
                "label": "Mantener bloqueado",
                "instruction": "Conservar esta tarea y su trabajo pendiente.",
                "action": "hold",
            },
        ]
        db.execute(
            "INSERT OR IGNORE INTO work_questions(id,workspace,title,options,task_id,created_at,source_task_id,source_revision,source_signature) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                qid,
                task["workspace"],
                LABELS[state] + ": " + request.get("title", "")[:150],
                json.dumps(options),
                task["id"],
                service.clock().isoformat(),
                task["id"],
                task["revision"],
                sig,
            ),
        )
    db.commit()
    for q in db.execute(
        "SELECT * FROM work_questions WHERE source_task_id IS NOT NULL AND selected IS NULL AND notice_sent=0"
    ).fetchall():
        # Durable deterministic IDs make a crash between chat and ledger commits safe.
        try:
            notify(service, q)
        except Exception as exc:
            # A failed notification must not stop unrelated project work.
            db.execute(
                "INSERT INTO work_meta(name,value) VALUES (?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value",
                ("decision_notice_error:" + q["id"], type(exc).__name__),
            )
            db.commit()
            continue
        db.execute("UPDATE work_questions SET notice_sent=1 WHERE id=?", (q["id"],))
        db.commit()


def notify(service, question):
    from backend.app.domain.entities.chat_message import (
        ChatMessage,
        ChatMessageRole,
        ChatMessageAuthorType,
        ChatMessageStatus,
    )

    session_id = str(uuid5(NAMESPACE_URL, "work-decisions:" + question["workspace"]))
    if not service.messages.get_session(session_id):
        service.messages.create_session(
            title="Decisiones del trabajo automático",
            workspace_path=question["workspace"],
            session_id=session_id,
        )
    message_id = str(uuid5(NAMESPACE_URL, "work-decision-notice:" + question["id"]))
    repo = service.messages._repository
    if repo.get_message(message_id):
        return
    reason = json.loads(question["options"])[0]["instruction"]
    repo.save_message(
        ChatMessage(
            id=message_id,
            session_id=session_id,
            role=ChatMessageRole.ASSISTANT,
            author_type=ChatMessageAuthorType.ASSISTANT,
            agent_label="Coordinador · decisión pendiente",
            status=ChatMessageStatus.COMPLETED,
            content=f"{question['title']}\n\n{reason}\n\nAbrí Trabajo → Decisiones en este proyecto. Podés pedir una comprobación sin publicar o mantener el bloqueo. La comprobación conserva la misma tarea y sus validaciones; no modifica credenciales ni descarta cambios.\n\nDecisión: {question['id']}",
            dedupe_key="work-decision:" + question["id"],
            created_at=service.clock(),
            updated_at=service.clock(),
        )
    )


def choose(service, db, question, option):
    task = db.execute(
        "SELECT * FROM work_tasks WHERE id=?", (question["source_task_id"],)
    ).fetchone()
    if (
        not task
        or signature(task) != question["source_signature"]
        or task["status"] != "blocked"
        or task["stop_requested"]
    ):
        raise WorkConflict(
            "El bloqueo cambió; actualizá las decisiones antes de continuar"
        )
    action = json.loads(question["options"])[option]["action"]
    if action == "diagnose":
        # Admission and diagnosis retain all original locks, policy, DEV/Git gates.
        # This action can never replay deployment or reset the recovery budget.
        if service._active(task["workspace"]):
            raise WorkConflict("El proyecto todavía tiene trabajos activos")
        db.execute(
            "UPDATE work_tasks SET status='queued',revision=revision+1,recovery_mode='diagnose',recovery_state='diagnosis_requested',updated_at=? WHERE id=?",
            (service.clock().isoformat(), task["id"]),
        )
    db.execute(
        "UPDATE work_questions SET selected=? WHERE id=?", (option, question["id"])
    )
    cancel_notice(service, question["id"])
    service._event(
        db,
        task["id"],
        "decision_" + action,
        "Decisión humana sobre la misma tarea; no autoriza publicación",
    )
    db.commit()
    return service._view(
        db.execute("SELECT * FROM work_tasks WHERE id=?", (task["id"],)).fetchone()
    )


def cancel_notice(service, question_id):
    """Cancel an unsent notice through the existing SQL outbox's event authority."""
    repo = service.messages._repository
    connector = getattr(repo, "_connect", None)
    if connector is None:
        return
    with connector() as chat:
        if chat.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='bridge_push_events'"
        ).fetchone():
            chat.execute(
                "UPDATE bridge_push_events SET cancelled_at=? WHERE message_id=? AND cancelled_at IS NULL",
                (
                    int(service.clock().timestamp() * 1000),
                    str(uuid5(NAMESPACE_URL, "work-decision-notice:" + question_id)),
                ),
            )
            chat.commit()
