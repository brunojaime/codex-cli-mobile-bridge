"""Private-tailnet device enrollment and the bridge adapter for Nienfos push."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import select
import shutil
import sqlite3
import subprocess
import threading
import time
from uuid import uuid4


class PushError(Exception):
    def __init__(self, message: str, status: int = 503):
        super().__init__(message)
        self.status = status


class PushNotificationService:
    def __init__(self, settings):
        self.settings = settings
        self.root = Path(__file__).resolve().parents[4]
        self.database = settings.chat_store_path
        self.environment = settings.bridge_environment
        self.bridge_id = hashlib.sha256(
            (self.environment + ":" + settings.chat_store_path).encode()
        ).hexdigest()[:24]
        self._lock = threading.RLock()
        self._process = None
        self._schema_ready = False

    @property
    def credential(self):
        value = (
            self.settings.codex_prod_firebase_service_account_json
            if self.environment == "prod"
            else self.settings.codex_dev_firebase_service_account_json
        )
        return value.get_secret_value() if value else None

    @property
    def configured(self):
        return bool(
            self.settings.push_notifications_enabled
            and self.credential
            and self.settings.chat_store_backend == "sqlite"
            and self.environment in {"dev", "prod"}
        )

    def connect(self):
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        if not self._schema_ready:
            with self._lock:
                db.executescript(
                    (
                        self.root / "services/notifications/migrations/001-push.sql"
                    ).read_text()
                )
                db.executescript((self.root / "services/notifications/migrations/002-trigger-idempotency.sql").read_text())
                self._schema_ready = True
        return db

    def start(self):
        if not self.configured:
            return
        with self._lock:
            if self._process and self._process.poll() is None:
                return
            with self.connect():
                pass
            node = self.settings.push_node_binary or shutil.which("node")
            if not node:
                raise PushError("No está disponible el proceso de notificaciones.")
            origin = "https://" + self.settings.push_origin_host
            child_env = {
                k: v
                for k, v in os.environ.items()
                if k in {"PATH", "HOME", "LANG", "TMPDIR", "NODE_EXTRA_CA_CERTS"}
            }
            child_env.update(
                CODEX_PUSH_DATABASE=self.database,
                CODEX_PUSH_ENVIRONMENT=self.environment,
                CODEX_PUSH_ORIGIN=origin,
                CODEX_PUSH_BRIDGE_ID=self.bridge_id,
                CODEX_PUSH_CREDENTIAL=self.credential,
            )
            self._process = subprocess.Popen(
                [
                    node,
                    "--disable-warning=ExperimentalWarning",
                    str(self.root / "services/notifications/src/worker.mjs"),
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                env=child_env,
                bufsize=1,
            )
            self.rpc("status")

    def close(self):
        with self._lock:
            if self._process:
                self._process.terminate()
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                self._process = None

    def rpc(self, method, **params):
        with self._lock:
            if not self._process or self._process.poll() is not None:
                self.start()
            process = self._process
            if not process:
                raise PushError("Push todavía no está configurado en este servidor.")
            request_id = str(uuid4())
            process.stdin.write(
                json.dumps({"id": request_id, "method": method, "params": params})
                + "\n"
            )
            process.stdin.flush()
            if not select.select([process.stdout], [], [], 35)[0]:
                self.close()
                raise PushError("El servicio de notificaciones no respondió a tiempo.")
            try:
                response = json.loads(process.stdout.readline())
            except (ValueError, OSError):
                raise PushError(
                    "El servicio de notificaciones no está disponible."
                ) from None
            if response.get("id") != request_id or response.get("error"):
                raise PushError("No se pudo completar la operación de notificaciones.")
            return response["result"]

    @staticmethod
    def trusted_network(host, origin=None):
        if origin:
            return False
        try:
            ip = ipaddress.ip_address(host)
            return (
                ip.is_loopback
                or ip in ipaddress.ip_network("100.64.0.0/10")
                or ip in ipaddress.ip_network("fd7a:115c:a1e0::/48")
            )
        except ValueError:
            return False

    def limit(self, bucket, maximum=12):
        now = int(time.time() * 1000)
        with self.connect() as db:
            db.execute(
                "INSERT INTO bridge_push_limits VALUES(?,1,?) ON CONFLICT(bucket) DO UPDATE SET count=CASE WHEN window_at<? THEN 1 ELSE count+1 END,window_at=CASE WHEN window_at<? THEN excluded.window_at ELSE window_at END",
                (bucket, now, now - 60000, now - 60000),
            )
            count = db.execute(
                "SELECT count FROM bridge_push_limits WHERE bucket=?", (bucket,)
            ).fetchone()[0]
        if count > maximum:
            raise PushError("Esperá un minuto antes de volver a intentar.", 429)

    def authenticate(self, bearer):
        if not bearer or not re.fullmatch(r"[A-Za-z0-9_-]{40,200}", bearer):
            raise PushError("Falta la autorización de este teléfono.", 401)
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM bridge_push_installations WHERE credential_hash=? AND enabled=1 AND updated_at>?",
                (
                    hashlib.sha256(bearer.encode()).hexdigest(),
                    int(time.time() * 1000) - 30 * 86400000,
                ),
            ).fetchone()
        if not row:
            raise PushError("Este teléfono ya no está autorizado.", 401)
        return dict(row)

    def register(self, installation_id, bearer, token, platform):
        if not self.configured:
            raise PushError("Push todavía no está configurado en este servidor.")
        # Validate bearer before storing it; never log the token or credential.
        if not re.fullmatch(r"[A-Za-z0-9_-]{40,200}", bearer or ""):
            raise PushError("Autorización de dispositivo inválida.", 401)
        digest = hashlib.sha256(bearer.encode()).hexdigest()
        now = int(time.time() * 1000)
        with self.connect() as db:
            row = db.execute(
                "SELECT credential_hash FROM bridge_push_installations WHERE id=?",
                (installation_id,),
            ).fetchone()
            if row and row[0] != digest:
                raise PushError("La instalación pertenece a otra autorización.", 409)
            db.execute(
                "INSERT INTO bridge_push_installations(id,credential_hash,created_at,updated_at) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET enabled=1,updated_at=excluded.updated_at",
                (installation_id, digest, now, now),
            )
        return self.rpc(
            "register",
            bearer=bearer,
            installationId=installation_id,
            token=token,
            platform=platform,
        )

    def revoke(self, device):
        with self.connect() as db:
            db.execute(
                "UPDATE bridge_push_installations SET enabled=0 WHERE id=?",
                (device["id"],),
            )
            db.execute(
                "UPDATE nienfos_push_outbox SET state='cancelled',fid='',title='',body='' WHERE installation_id=? AND state='pending'",
                (device["id"],),
            )
            db.execute(
                "DELETE FROM nienfos_push_devices WHERE installation_id=?",
                (device["id"],),
            )

    def read(self, device, session_id, whole_project=False):
        now = int(time.time() * 1000)
        with self.connect() as db:
            session = db.execute(
                "SELECT workspace_path FROM sessions WHERE id=?", (session_id,)
            ).fetchone()
            if not session:
                raise PushError("Chat no encontrado.", 404)
            resource = (
                ("project:" + session[0]) if whole_project else ("chat:" + session_id)
            )
            db.execute(
                "INSERT INTO bridge_push_reads VALUES(?,?,?) ON CONFLICT(installation_id,resource) DO UPDATE SET read_at=excluded.read_at",
                (device["id"], resource, now),
            )
            db.execute(
                "UPDATE bridge_push_installations SET updated_at=? WHERE id=?",
                (now, device["id"]),
            )
            db.execute(
                "UPDATE nienfos_push_outbox SET state='cancelled',fid='',title='',body='' WHERE installation_id=? AND state='pending' AND event_id IN (SELECT e.id FROM bridge_push_events e JOIN sessions s ON s.id=e.session_id WHERE (CASE WHEN ? THEN s.workspace_path=? ELSE s.id=? END) AND COALESCE(e.ready_at,e.created_at)<=?)",
                (device["id"], int(whole_project), session[0], session_id, now),
            )

    def test(self, device):
        self.limit("test:" + device["id"], 3)
        event_id = uuid4().hex
        now = int(time.time() * 1000)
        with self.connect() as db:
            db.execute(
                "INSERT INTO bridge_push_events(id,event_key,installation_id,kind,created_at,ready_at) VALUES(?,?,?,'device.test',?,?)",
                (event_id, "test:" + event_id, device["id"], now, now),
            )
        self.rpc("tick")
        return {"event_id": event_id, "status": "queued"}

    def event(self, device, event_id):
        with self.connect() as db:
            event = db.execute(
                "SELECT e.* FROM bridge_push_events e JOIN nienfos_push_outbox o ON o.event_id=e.id WHERE e.id=? AND o.installation_id=?",
                (event_id, device["id"]),
            ).fetchone()
            if not event or event["cancelled_at"]:
                raise PushError("El aviso ya no está disponible.", 410)
            if event["kind"] == "device.test":
                if event["installation_id"] != device["id"]:
                    raise PushError("Aviso no disponible.", 404)
                return {
                    "event_id": event_id,
                    "test": True,
                    "title": "Notificaciones activas",
                    "body": "Este teléfono ya puede recibir avisos de tus proyectos.",
                }
            row = db.execute(
                "SELECT m.*,s.title,s.workspace_name,s.workspace_path FROM messages m JOIN sessions s ON s.id=m.session_id WHERE m.id=? AND s.archived_at IS NULL",
                (event["message_id"],),
            ).fetchone()
            if not row:
                raise PushError("El mensaje ya no está disponible.", 410)
            read = db.execute(
                "SELECT 1 FROM bridge_push_reads WHERE installation_id=? AND resource IN (?,?) AND read_at>=?",
                (
                    device["id"],
                    "chat:" + row["session_id"],
                    "project:" + row["workspace_path"],
                    event["ready_at"] or event["created_at"],
                ),
            ).fetchone()
            if read:
                raise PushError("Este aviso ya fue leído.", 410)
            preview = re.sub(
                r"\s+", " ", re.sub(r"[`#*>]", "", row["content"] or "")
            ).strip()
            if len(preview) > 160:
                preview = preview[:157] + "..."
            status = (
                "Necesita atención"
                if row["status"] == "failed"
                else "Trabajo finalizado"
            )
            return {
                "event_id": event_id,
                "test": False,
                "title": row["workspace_name"],
                "body": f"{row['title']} · {status}\n{preview or 'Tocá para leer la respuesta.'}",
                "summary": status,
                "session_id": row["session_id"],
                "workspace_path": row["workspace_path"],
                "message_id": row["id"],
                "job_id": row["job_id"] or row["id"],
            }

    def receipt(self, device, event_id):
        event = self.event(device, event_id)
        now = int(time.time() * 1000)
        with self.connect() as db:
            if event["test"]:
                db.execute(
                    "UPDATE bridge_push_installations SET verified_at=?,updated_at=? WHERE id=?",
                    (now, now, device["id"]),
                )
        return {
            "received": True,
            "device_verified": bool(event["test"] or device["verified_at"]),
        }

    def logo(self, session_id):
        with self.connect() as db:
            session = db.execute(
                "SELECT workspace_path FROM sessions WHERE id=?", (session_id,)
            ).fetchone()
            if not session:
                raise PushError("Chat no encontrado.", 404)
            root = Path(session[0]).resolve()
            configured = db.execute(
                "SELECT relative_path FROM bridge_project_logos WHERE workspace_path=?",
                (str(root),),
            ).fetchone()
        candidates = ([configured[0]] if configured else []) + [
            ".codex/project-logo.png",
            "assets/branding/app_icon.png",
            "frontend/mobile_app/assets/branding/app_icon.png",
            "assets/logo.png",
            "frontend/assets/logo.png",
            "apps/web/static/brand/logo.png",
            "static/logo.png",
            "public/logo.png",
        ]
        for relative in candidates:
            path = (root / relative).resolve()
            if (
                path.is_relative_to(root)
                and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
                and path.is_file()
                and path.stat().st_size <= 512 * 1024
            ):
                return path
        raise PushError("Este proyecto todavía no tiene un logo asociado.", 404)

    def set_logo(self, session_id, relative_path):
        with self.connect() as db:
            row = db.execute(
                "SELECT workspace_path FROM sessions WHERE id=?", (session_id,)
            ).fetchone()
            if not row:
                raise PushError("Chat no encontrado.", 404)
            root = Path(row[0]).resolve()
            path = (root / relative_path).resolve()
            if (
                Path(relative_path).is_absolute()
                or not path.is_relative_to(root)
                or path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}
                or not path.is_file()
                or path.stat().st_size > 512 * 1024
            ):
                raise PushError(
                    "Elegí una imagen PNG, JPG o WebP del proyecto, de hasta 512 KB.",
                    422,
                )
            db.execute(
                "INSERT INTO bridge_project_logos VALUES(?,?,?) ON CONFLICT(workspace_path) DO UPDATE SET relative_path=excluded.relative_path,updated_at=excluded.updated_at",
                (str(root), str(path.relative_to(root)), int(time.time() * 1000)),
            )
        return {"ok": True}

    def upload_logo(self, session_id, data):
        if len(data) > 512 * 1024:
            raise PushError("La imagen debe pesar hasta 512 KB.", 422)
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            extension = ".png"
        elif data.startswith(b"\xff\xd8\xff"):
            extension = ".jpg"
        elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
            extension = ".webp"
        else:
            raise PushError("Elegí una imagen PNG, JPG o WebP.", 422)
        with self.connect() as db:
            row = db.execute(
                "SELECT workspace_path FROM sessions WHERE id=?", (session_id,)
            ).fetchone()
            if not row:
                raise PushError("Chat no encontrado.", 404)
        root = Path(row[0]).resolve()
        directory = root / ".codex"
        if not directory.resolve().is_relative_to(root):
            raise PushError("La carpeta del logo no pertenece al proyecto.", 403)
        directory.mkdir(exist_ok=True)
        destination = directory / ("project-logo" + extension)
        if destination.is_symlink():
            raise PushError("No se puede reemplazar un enlace del proyecto.", 403)
        temporary = directory / ("logo-" + uuid4().hex + ".tmp")
        try:
            temporary.write_bytes(data)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        return self.set_logo(session_id, str(destination.relative_to(root)))
