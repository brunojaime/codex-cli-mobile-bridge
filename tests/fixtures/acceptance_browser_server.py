"""Loopback-only application for acceptance tests, never a product deployment."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import hashlib
import json
import runpy
import sqlite3

ROOT = Path.cwd()
DATA = ROOT / ".runtime"
DATA.mkdir(exist_ok=True)
with sqlite3.connect(DATA / "clients.sqlite") as db:
    db.execute(
        "CREATE TABLE IF NOT EXISTS clients (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"
    )

PAGE = """<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Prueba local de aceptación</title><style>
body{font:16px system-ui;background:#f3f6fa;color:#17314d;margin:0;padding:24px}main{max-width:520px;margin:auto}
.badge{font-size:12px;font-weight:700;color:#7a4400;background:#ffecd0;padding:10px;border-radius:8px}
section{background:white;border:1px solid #d8e1ec;border-radius:14px;padding:20px;margin-top:20px}
input,button{box-sizing:border-box;font:inherit;width:100%;padding:12px;border:1px solid #aabccc;border-radius:8px;margin-top:8px;min-height:44px}
button{background:#184b77;color:white}li{padding:12px 0}small{color:#57697b}</style>
<main><p class="badge">LABORATORIO LOCAL · DATOS DE PRUEBA</p><h1>Guardar y volver</h1>
<p>Este caso comprueba persistencia y visibilidad. No es Gestión publicada.</p>
<section><h2>Crear cliente</h2><form><label for="name">Nombre de prueba</label><input id="name" required><button>Guardar cliente</button></form><p id="saved" aria-live="polite"></p></section>
<section><h2>Cartera</h2><ul id="clients"></ul><p id="empty" hidden>No hay clientes visibles.</p><small id="loaded">Cargando…</small></section></main>
<script>
async function refresh(){const rows=await fetch('/api/clients').then(r=>r.json());const ul=document.querySelector('#clients');ul.replaceChildren();for(const row of rows){const li=document.createElement('li');li.dataset.clientId=row.id;li.textContent=row.name;ul.append(li);}document.querySelector('#empty').hidden=!!rows.length;document.querySelector('#loaded').textContent='Lista actualizada';}
document.querySelector('form').onsubmit=async e=>{e.preventDefault();const response=await fetch('/api/clients',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({name:document.querySelector('#name').value})});const row=await response.json();document.querySelector('#saved').textContent='Cliente guardado';document.querySelector('#saved').dataset.id=row.id;await refresh();};refresh();
</script></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def send(self, value, content_type="application/json"):
        body = value.encode() if isinstance(value, str) else json.dumps(value).encode()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            return self.send(PAGE, "text/html; charset=utf-8")
        if self.path == "/version":
            return self.send(
                {
                    "release_id": hashlib.sha256(
                        (ROOT / "listing.py").read_bytes()
                    ).hexdigest()
                }
            )
        with sqlite3.connect(DATA / "clients.sqlite") as db:
            rows = [
                {"id": r[0], "name": r[1]}
                for r in db.execute("SELECT id,name FROM clients")
            ]
        if self.path == "/api/clients":
            rows = runpy.run_path(str(ROOT / "listing.py"))["list_clients"](rows)
            return self.send(rows)
        if self.path.startswith("/api/clients/"):
            return self.send(
                next(
                    (r for r in rows if str(r["id"]) == self.path.rsplit("/", 1)[-1]),
                    None,
                )
            )
        self.send_error(404)

    def do_POST(self):
        if self.path != "/api/clients":
            return self.send_error(404)
        data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        with sqlite3.connect(DATA / "clients.sqlite") as db:
            id = db.execute(
                "INSERT INTO clients(name) VALUES (?)", (data["name"],)
            ).lastrowid
        self.send({"id": id})


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    (DATA / "port").write_text(str(server.server_port))
    server.serve_forever()
