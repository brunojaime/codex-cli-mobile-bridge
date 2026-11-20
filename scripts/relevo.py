#!/usr/bin/env python3
"""Relevo: pasar el trabajo en curso de este equipo a otro (Batata, Mac...) y volver.

Uso (todo por defecto, pensado para dispararlo desde un chat):
  relevo.py ir batata                 # pasa los proyectos con chats recientes
  relevo.py ir batata --proyecto RUTA # sólo ese proyecto
  relevo.py ir batata --simular       # muestra el plan sin tocar nada
  relevo.py volver batata             # pide a Batata que suba lo suyo y lo trae
  relevo.py traer batata              # sólo trae ramas relevo/batata-* ya subidas
  relevo.py estado

Garantías:
- No toca rama, índice ni árbol de trabajo locales: el WIP se captura con un
  índice temporal y se publica como rama relevo/<origen>-<fecha> en GitHub.
- No viajan secretos (.env, .dev.vars, claves...). Sólo se informan nombres
  de archivo y de variable para que el destino los compare.
- El resumen de chats es determinista (sin llamar a un modelo).
- La vuelta trae una rama aparte; nunca hace merge automático.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOSTS_FILE = Path(os.environ.get("RELEVO_HOSTS_FILE", ROOT / "config" / "relevo-hosts.json"))
STATE_FILE = Path(os.environ.get("RELEVO_STATE_FILE", Path.home() / ".local/state/relevo/relevos.json"))

SECRET_PATTERNS = [
    ".env", ".env.*", "*.env", ".dev.vars", ".dev.vars.*", "*.pem", "*.key", "*.p12",
    "*.keystore", "*.jks", "id_rsa*", "id_ed25519*", "credentials*.json",
    "service-account*.json", "*.sqlite3-wal", ".npmrc", ".netrc", "secrets.*",
]
SECRET_DIRS = {".private", ".secrets", "node_modules", ".wrangler", ".venv", "venv"}
MAX_FILE_BYTES = 50 * 1024 * 1024
REDACT = re.compile(
    r"(?i)((?:pass(?:word)?|pwd|token|secret|api[_-]?key|authorization|bearer)\s*[:=]?\s*)(\S{4,})"
)
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


# ---------------------------------------------------------------- utilidades
def now_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def run(cmd: list[str], cwd: Path | None = None, env: dict | None = None,
        check: bool = True, timeout: int = 120) -> str:
    res = subprocess.run(cmd, cwd=cwd, env=env, text=True, capture_output=True, timeout=timeout)
    if check and res.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:4])}… falló: {res.stderr.strip()[-400:]}")
    return res.stdout.strip()


def redact(text: str) -> str:
    return REDACT.sub(lambda m: m.group(1) + "[oculto]", text or "")


def is_secret_path(rel: str) -> bool:
    parts = rel.split("/")
    if any(p in SECRET_DIRS for p in parts[:-1]):
        return True
    name = parts[-1]
    return any(fnmatch.fnmatch(name, pat) for pat in SECRET_PATTERNS) and name not in {
        ".env.example", ".env.sample", ".env.template", ".dev.vars.example"
    }


def load_hosts() -> dict:
    return json.loads(HOSTS_FILE.read_text())["hosts"]


def self_host(hosts: dict) -> str:
    name = socket.gethostname().lower()
    for key, cfg in hosts.items():
        if any(name == h.lower() for h in cfg.get("match_hostnames", [])):
            return key
    raise SystemExit(f"Este equipo ({name}) no figura en {HOSTS_FILE}")


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"relevos": []}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    tmp.replace(STATE_FILE)


# --------------------------------------------------------------- HTTP bridge
def http(method: str, url: str, body: dict | None = None, socks5: str | None = None,
         timeout: int = 30):
    if socks5:
        cmd = ["curl", "-sS", "-m", str(timeout), "--socks5-hostname", socks5, "-X", method,
               "-H", "Content-Type: application/json", "-w", "\n%{http_code}", url]
        if body is not None:
            cmd += ["--data-binary", "@-"]
        res = subprocess.run(cmd, input=json.dumps(body) if body is not None else None,
                             text=True, capture_output=True, timeout=timeout + 5)
        if res.returncode != 0:
            raise RuntimeError(f"{url}: {res.stderr.strip()[-200:]}")
        payload, _, code = res.stdout.rpartition("\n")
        if not code.startswith("2"):
            raise RuntimeError(f"{url}: HTTP {code} {payload[:300]}")
        return json.loads(payload) if payload else None
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else None


# ----------------------------------------------------------------- git
def git(repo: Path, *args: str, env: dict | None = None, check: bool = True, timeout: int = 180) -> str:
    return run(["git", "-C", str(repo), *args], env=env, check=check, timeout=timeout)


def repo_info(path: Path) -> dict | None:
    try:
        top = Path(git(path, "rev-parse", "--show-toplevel"))
    except Exception:
        return None
    remote = git(top, "remote", "get-url", "origin", check=False)
    branch = git(top, "rev-parse", "--abbrev-ref", "HEAD", check=False) or "HEAD"
    head = git(top, "rev-parse", "--verify", "HEAD", check=False)
    m = re.search(r"/([^/]+?)(?:\.git)?/?$", remote or "")
    # En el destino se usa el nombre del repo de GitHub (patsa-local -> patsa).
    name = m.group(1) if m else top.name
    return {"path": str(top), "name": name, "local_name": top.name, "remote": remote,
            "branch": branch, "head": head}


def snapshot(repo: Path, label: str, source_host: str) -> dict:
    """Commit con todo el WIP (incl. archivos nuevos no ignorados) sin tocar el índice real."""
    head = git(repo, "rev-parse", "--verify", "HEAD", check=False)
    excluded: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(tmp) / "index"))
        if head:
            git(repo, "read-tree", head, env=env)
        git(repo, "add", "-A", "--", ".", env=env, timeout=600)
        if head:
            changed = git(repo, "diff", "--cached", "--name-only", "--no-renames", head, env=env).splitlines()
        else:
            changed = git(repo, "ls-files", env=env).splitlines()
        for rel in changed:
            fp = repo / rel
            too_big = fp.is_file() and fp.stat().st_size > MAX_FILE_BYTES
            if is_secret_path(rel) or too_big:
                excluded.append(rel + (" (más de 50 MB)" if too_big else " (secreto)"))
                if head:  # vuelve a la versión de HEAD (o la quita si no estaba)
                    git(repo, "reset", "-q", head, "--", rel, env=env)
                else:
                    git(repo, "update-index", "--force-remove", "--", rel, env=env)
        # Repos anidados (gitlinks nuevos) no se suben como submódulo fantasma.
        for line in git(repo, "ls-files", "-s", env=env).splitlines():
            meta, rel = line.split("\t", 1)
            if meta.startswith("160000") and rel in changed and not (
                    head and subprocess.run(["git", "-C", str(repo), "cat-file", "-e", f"{head}:{rel}"],
                                            capture_output=True).returncode == 0):
                excluded.append(rel + " (repo git anidado: pasalo con --proyecto)")
                git(repo, "update-index", "--force-remove", "--", rel, env=env)
        tree = git(repo, "write-tree", env=env)
    head_tree = git(repo, "rev-parse", f"{head}^{{tree}}") if head else None
    files_changed = [c for c in changed if not any(c == e.split(" (")[0] for e in excluded)]
    if head and tree == head_tree:
        commit = head
    else:
        msg = f"relevo: WIP de {source_host} ({label})\n\nCapturado sin modificar el árbol de trabajo de origen."
        cmd = ["commit-tree", tree, "-m", msg] + (["-p", head] if head else [])
        commit = git(repo, *cmd, env=dict(os.environ, GIT_AUTHOR_NAME=git(repo, "config", "user.name", check=False) or "relevo",
                                          GIT_AUTHOR_EMAIL=git(repo, "config", "user.email", check=False) or "relevo@localhost",
                                          GIT_COMMITTER_NAME=git(repo, "config", "user.name", check=False) or "relevo",
                                          GIT_COMMITTER_EMAIL=git(repo, "config", "user.email", check=False) or "relevo@localhost"))
    return {"commit": commit, "tree": tree, "base": head, "wip_files": files_changed, "excluded": excluded}


def secret_inventory(repo: Path) -> list[dict]:
    """Nombres de archivos de secretos ignorados y nombres de variables (sin valores)."""
    out = git(repo, "ls-files", "--others", "--ignored", "--exclude-standard", "--directory", check=False)
    found = []
    for rel in out.splitlines():
        rel = rel.rstrip("/")
        if "node_modules" in rel or not is_secret_path(rel):
            continue
        fp = repo / rel
        keys: list[str] = []
        if fp.is_file() and fp.stat().st_size < 200_000 and ("env" in fp.name or "vars" in fp.name):
            for line in fp.read_text(errors="ignore").splitlines():
                m = re.match(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
                if m:
                    keys.append(m.group(1))
        found.append({"file": rel, "keys": keys})
    return found[:40]


def repo_visibility(remote: str) -> str:
    m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?/?$", remote)
    if not m:
        return "desconocida"
    res = subprocess.run(["gh", "repo", "view", m.group(1), "--json", "visibility", "-q", ".visibility"],
                         text=True, capture_output=True, timeout=30)
    return res.stdout.strip().lower() or "desconocida"


# ------------------------------------------------------------ chats/servicios
def ancestor_uuids() -> set[str]:
    ids: set[str] = set()
    for var in ("CLAUDE_CODE_SESSION_ID", "CODEX_SESSION_ID", "CODEX_THREAD_ID"):
        if os.environ.get(var):
            ids.add(os.environ[var])
    pid = os.getpid()
    for _ in range(30):
        try:
            cmd = Path(f"/proc/{pid}/cmdline").read_bytes().decode(errors="ignore")
            ids.update(UUID.findall(cmd))
            pid = int(re.search(r"PPid:\s+(\d+)", Path(f"/proc/{pid}/status").read_text()).group(1))
        except Exception:
            break
        if pid <= 1:
            break
    return ids


def local_sessions(bridges: list[str]) -> list[dict]:
    sessions = []
    for base in bridges:
        try:
            for s in http("GET", base + "/sessions", timeout=15) or []:
                if not s.get("archived_at"):
                    s["_bridge"] = base
                    sessions.append(s)
        except Exception as exc:
            log(f"  aviso: no pude leer {base}: {exc}")
    return sessions


def is_own_session(detail: dict, own: set[str]) -> bool:
    candidates = {detail.get("id"), (detail.get("provider_session_id") or "").split(":")[-1]}
    return bool(candidates & own)


def summarize_session(detail: dict, limit: int = 6, closing: str | None = None) -> str:
    msgs = [m for m in detail.get("messages", []) if m.get("visibility", "visible") == "visible"
            and m.get("role") in ("user", "assistant") and (m.get("content") or "").strip()]
    lines = [f"### Chat «{detail.get('title') or 'sin título'}» (id {detail['id'][:8]})"]
    if closing:
        lines.append("**Resumen de cierre del agente:**\n" + closing)
        lines.append("Últimos mensajes:")
    for m in msgs[-limit:]:
        who = "Bruno" if m["role"] == "user" else "Agente"
        text = redact(" ".join(m["content"].split()))
        lines.append(f"- **{who}:** {text[:700]}{'…' if len(text) > 700 else ''}")
    return "\n".join(lines)


CLOSE_MESSAGE = """RELEVO EN CURSO: Bruno pasa este trabajo a otro equipo ahora.
- Terminá el paso que estás haciendo y llegá a un punto seguro. No empieces nada nuevo.
- Dejá los archivos guardados (el relevo captura los cambios sin commit). No hagas commit, push, deploy ni reinicios.
- NO ejecutes `relevo` ni intentes hacer el pasaje vos: ya lo está haciendo el sistema.
- Terminá tu respuesta con este bloque (corto, sin secretos):
RELEVO_CIERRE
Objetivo: ...
Hecho: ...
Pendiente: ...
Próximo paso: ...
"""
ACTIVE_JOB = ("pending", "running", "queued")


def active_jobs(detail: dict) -> list[str]:
    run = detail.get("current_run") or {}
    if not run.get("is_active"):
        return []
    return [st["job_id"] for st in run.get("stages", [])
            if st.get("job_id") and st.get("job_status") in ACTIVE_JOB]


def closing_summary(detail: dict) -> str | None:
    for m in reversed(detail.get("messages", [])):
        text = m.get("content") or ""
        if m.get("role") == "assistant" and "RELEVO_CIERRE" in text:
            return redact(text.split("RELEVO_CIERRE", 1)[1].strip())[:2500]
    return None


def close_sessions(items: list[tuple[str, dict]], wait_s: int, poll_s: int = 5) -> dict[str, dict]:
    """Cierre ordenado: steering a todos, espera en paralelo y cancelación sólo como último recurso."""
    out: dict[str, dict] = {}
    for base, detail in items:
        jobs = active_jobs(detail)
        if not jobs:
            out[detail["id"]] = {"via": "inactivo", "base": base}
            continue
        steered, why, queued = False, "", False
        for job in jobs:
            try:
                http("POST", f"{base}/jobs/{job}/steer", {"message": CLOSE_MESSAGE}, timeout=20)
                steered = True
            except Exception as exc:
                why = str(exc)[-160:]
        if not steered:
            # Sin steering para ese proveedor: el cierre queda como siguiente turno del mismo
            # chat (el Bridge lo encola hasta que termine el turno actual, sin cortarlo).
            try:
                http("POST", f"{base}/message", {"message": CLOSE_MESSAGE, "session_id": detail["id"],
                     "workspace_path": detail.get("workspace_path")}, timeout=30)
                queued = True
            except Exception as exc:
                why += f"; no se pudo encolar: {str(exc)[-120:]}"
        out[detail["id"]] = {"via": None, "base": base, "steered": steered, "queued": queued, "why": why}
    deadline = time.time() + wait_s
    pending = [sid for sid, r in out.items() if r["via"] is None]
    while pending and time.time() < deadline:
        time.sleep(poll_s)
        for sid in list(pending):
            r = out[sid]
            try:
                d = http("GET", f"{r['base']}/sessions/{sid}", timeout=20)
            except Exception:
                continue
            if not active_jobs(d):
                r["via"] = ("cerró por steering" if r["steered"] else
                            "cerró con mensaje de cierre encolado (steering no disponible)" if r["queued"] else
                            "terminó solo (steering no disponible)")
                r["summary"] = closing_summary(d)
                pending.remove(sid)
    for sid in pending:
        r = out[sid]
        d = http("GET", f"{r['base']}/sessions/{sid}", timeout=20)
        for job in active_jobs(d):
            try:
                http("POST", f"{r['base']}/jobs/{job}/cancel", {}, timeout=20)
            except Exception:
                pass
        r["via"] = ("cancelado tras espera" + ("" if r["steered"] else f" (steering no disponible: {r['why']})"))
        r["summary"] = closing_summary(d)
    return out


def running_services(repo: Path) -> list[str]:
    out = []
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            cwd = os.readlink(proc / "cwd")
            if not (cwd == str(repo) or cwd.startswith(str(repo) + "/")):
                continue
            argv = (proc / "cmdline").read_bytes().split(b"\0")
            argv = [a.decode(errors="ignore") for a in argv if a]
            if not argv or Path(argv[0]).name in ("bash", "sh", "zsh", "git", "esbuild", "workerd",
                                                 "claude", "codex", "python3-relevo"):
                continue
            short = " ".join([Path(argv[0]).name] + argv[1:])
            out.append(f"(en {os.path.relpath(cwd, repo)}) " + redact(short)[:200])
        except Exception:
            continue
    return sorted(set(out))[:15]


# ------------------------------------------------------------------ ir
FULL_ACCESS = {"config_overrides": ['sandbox_mode="danger-full-access"']}


def work_dir(info: dict, dest: dict, on_dest: bool) -> str:
    base = f"{dest['projects_root']}/{info['name']}"
    return f"{base}-relevo" if on_dest else base


def prep_message(info: dict, snap: dict, branch: str, dest: dict, src: str, on_dest: bool) -> str:
    """Fase 1 (acceso completo, sólo comandos acotados): traer y verificar el código."""
    repo_dir = f"{dest['projects_root']}/{info['name']}"
    work = work_dir(info, dest, on_dest)
    if on_dest:
        steps = f"""1. `cd {repo_dir} && git fetch {info['remote']} {branch}`; `git rev-parse FETCH_HEAD` debe ser `{snap['commit']}`.
2. NO toques la rama ni los cambios de `{repo_dir}`. Si `{work}` no existe: `git -C {repo_dir} worktree add -B {branch} {work} {snap['commit']}`.
   Si existe y `git -C {work} status --porcelain` está vacío: `git -C {work} switch -C {branch} {snap['commit']}`.
   Si tiene cambios: NO lo pises; terminá con RELEVO_FALLO worktree-con-cambios.
3. Secretos: por cada archivo ignorado de secretos que exista en `{repo_dir}` y falte en `{work}`, copialo con `cp -p` y `chmod 600`. Nunca muestres valores."""
    else:
        steps = f"""1. Si `{work}` NO existe: `git clone {info['remote']} {work}`. Si existe, no lo borres: terminá con RELEVO_FALLO ya-existe.
2. `git -C {work} switch -c {branch} origin/{branch}`; `git -C {work} rev-parse HEAD` debe ser `{snap['commit']}`."""
    return f"""RELEVO {src} → este equipo, fase de preparación. Ejecutá SÓLO estos comandos, sin publicar, sin reiniciar servicios ni tocar otros proyectos:
{steps}
Última línea de tu respuesta, exactamente una de:
RELEVO_LISTO {work} <hash de HEAD>
RELEVO_FALLO <motivo corto>"""


def context_message(info: dict, snap: dict, branch: str, dest_name: str, src: str, work: str,
                    chats: list[str], services: list[str], secrets: list[dict]) -> str:
    """Fase 2: chat de continuación abierto directamente en la carpeta de trabajo."""
    sec = "\n".join(f"- `{s['file']}`: {', '.join(s['keys']) or '(sin variables legibles)'}" for s in secrets) or "- ninguno"
    svc = "\n".join(f"- {s}" for s in services) or "- ninguno"
    wip = ", ".join(snap["wip_files"][:25]) or "sin cambios sin commit"
    exc = ", ".join(snap["excluded"][:15]) or "nada"
    body = f"""RELEVO desde {src}: Bruno sigue acá el trabajo de **{info['name']}** (en {src} se quedó sin internet).
Carpeta: `{work}` · rama `{branch}` · commit `{snap['commit']}` (ya clonado y verificado).
Rama original en {src}: `{info['branch']}` · base `{(snap['base'] or '')[:12]}` · WIP incluido: {wip}. No viajaron: {exc}.

Ahora sólo: comprobá `git rev-parse HEAD` = `{snap['commit']}`; comprobá por NOMBRE (sin mostrar valores) qué secretos de la lista faltan acá; y respondé en 3 líneas: carpeta, hash ok, secretos faltantes (Bruno los carga desde el panel Secrets). Después esperá instrucciones de Bruno.

Secretos que había en {src} (sólo nombres):
{sec}

Servicios que corrían en {src} (levantalos sólo si Bruno lo pide):
{svc}

Para volver a {src}: cuando Bruno lo pida, `git add -A` (sin secretos), commit y `git push origin HEAD:refs/heads/relevo/{dest_name}-<AAAAMMDD-HHMMSS>`; respondé rama y hash. Sin merge.

## Contexto de los chats en {src}
"""
    budget = 9500 - len(body)
    ctx = ""
    for c in chats:
        if len(ctx) + len(c) + 2 > budget:
            ctx += "\n(…contexto recortado por tamaño)"
            break
        ctx += c + "\n\n"
    return body + (ctx or "(sin chats recientes)")


def wait_reply(bridge: str, session_id: str, socks: str | None, timeout_s: int) -> str:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        time.sleep(10)
        try:
            d = http("GET", f"{bridge}/sessions/{session_id}", socks5=socks, timeout=20)
        except Exception:
            continue
        if not (d.get("current_run") or {}).get("is_active"):
            msgs = [m for m in d.get("messages", []) if m.get("role") == "assistant"]
            return (msgs[-1].get("content") or "") if msgs else ""
    return ""


def cmd_ir(args) -> int:
    hosts = load_hosts()
    src = self_host(hosts)
    dest_name = args.destino
    dest = hosts.get(dest_name)
    if not dest or dest.get("enabled") is False or not dest.get("bridges"):
        raise SystemExit(f"Destino «{dest_name}» no configurado en {HOSTS_FILE}")
    me = hosts[src]
    dest_bridge, socks = dest["bridges"][0], dest.get("socks5")
    stamp = now_stamp()
    branch = f"relevo/{src}-{stamp}"
    state = load_state()
    # Con --todo (botón de la app) no hay chat disparador: se cierran todos los chats activos.
    own = set() if args.todo else ancestor_uuids()
    sessions = local_sessions(me["bridges"])
    since = time.time() - args.horas * 3600

    def recent(s):
        try:
            ts = dt.datetime.fromisoformat(s["updated_at"].replace("Z", "+00:00")).timestamp()
        except Exception:
            ts = 0
        return ts >= since or s.get("active_agent_run_id")

    if args.proyecto:
        targets = [Path(p).resolve() for p in args.proyecto]
    else:
        targets = sorted({Path(s["workspace_path"]) for s in sessions if recent(s) and s.get("workspace_path")})
    log(f"Relevo {src} → {dest_name} · {len(targets)} proyecto(s) · rama {branch}")
    try:
        dest_ws = {w["path"] for w in http("GET", dest_bridge + "/workspaces", socks5=socks, timeout=20)}
    except Exception as exc:
        raise SystemExit(f"No llego al Bridge de {dest_name} ({exc}). El relevo necesita internet ahora.")

    # Cierre ordenado ANTES de capturar el WIP: así viajan los últimos cambios de cada agente.
    target_roots = set()
    for t in targets:
        # Se compara con la carpeta exacta del workspace y con la raíz de su repo (si la hay).
        target_roots.add(Path(t).resolve())
        inf = repo_info(t)
        if inf and Path(inf["path"]) != Path(t).resolve() and args.proyecto:
            target_roots.add(Path(inf["path"]))
    to_close, own_ids = [], set()
    for s in sessions:
        wp = s.get("workspace_path")
        if not wp or not recent(s) or not any(Path(wp).resolve() == r for r in target_roots):
            continue
        detail = http("GET", f"{s['_bridge']}/sessions/{s['id']}", timeout=30)
        if is_own_session(detail, own):
            own_ids.add(s["id"])
        elif active_jobs(detail):
            to_close.append((s["_bridge"], detail))
    if to_close and not args.simular:
        log(f"Cerrando {len(to_close)} chat(s) activos por steering (hasta {args.esperar}s)…")
    closed = {} if args.simular else close_sessions(to_close, args.esperar)

    def collect_chats(*roots: Path) -> tuple[list[str], list[str]]:
        chats, frozen, wanted = [], [], {Path(r).resolve() for r in roots}
        for s in sessions:
            wp = s.get("workspace_path")
            if not wp or Path(wp).resolve() not in wanted or not recent(s):
                continue
            detail = http("GET", f"{s['_bridge']}/sessions/{s['id']}", timeout=30)
            r = closed.get(s["id"], {})
            if s["id"] in own_ids:
                frozen.append(f"{s['id'][:8]}: chat que disparó el relevo (no se frena)")
            elif args.simular and active_jobs(detail):
                frozen.append(f"{s['id'][:8]}: activo (se cerraría por steering)")
            else:
                frozen.append(f"{s['id'][:8]}: {r.get('via', 'inactivo')}")
            chats.append(summarize_session(detail, closing=r.get("summary")))
        return chats, frozen

    report, pending, context_only = [], [], []
    for target in targets:
        info = repo_info(target)
        row = {"proyecto": str(target), "estado": "", "rama": None}
        report.append(row)
        skip = None
        if not info or not info["remote"] or "github.com" not in info["remote"]:
            skip = "sin repositorio git con remoto GitHub"
        elif repo_visibility(info["remote"]) != "private" and not args.permitir_publico:
            skip = "el repo no es privado; el WIP no se sube a un repo público"
        if skip:
            # El código no viaja, pero los chats igual se cierran y siguen en el destino con su contexto.
            root = Path(target).resolve()
            chats, frozen = collect_chats(root)
            row.update(estado=f"WIP quedó en {src} ({skip})", chats=frozen)
            if chats and not args.simular:
                context_only.append((row, root.name, chats))
            continue
        repo = Path(info["path"])
        snap = snapshot(repo, stamp, src)
        prev = next((r for r in reversed(state["relevos"]) if r["repo"] == info["path"]
                     and r["dest"] == dest_name and r.get("kind") == "ir" and r.get("phase") == "listo"), None)
        if prev and prev.get("tree") == snap["tree"] and prev.get("base") == snap["base"] and not args.forzar:
            row.update(estado="sin cambios desde el último relevo: ya está en " + dest_name,
                       rama=prev["branch"], commit=prev["commit"], chat_destino=prev.get("dest_session"))
            continue
        chats, frozen = collect_chats(repo, Path(target))
        services = running_services(repo)
        secrets = secret_inventory(repo)
        on_dest = f"{dest['projects_root']}/{info['name']}" in dest_ws
        work = work_dir(info, dest, on_dest)
        prep = prep_message(info, snap, branch, dest, src, on_dest)
        msg = context_message(info, snap, branch, dest_name, src, work, chats, services, secrets)
        row.update(rama=branch, commit=snap["commit"], wip=len(snap["wip_files"]),
                   excluidos=snap["excluded"], chats=frozen, servicios=services,
                   secretos=[s["file"] for s in secrets], carpeta_destino=work, mensaje_chars=len(msg))
        if args.simular:
            row.update(estado="simulado", preparacion=prep, mensaje=msg)
            continue
        log(f"Subiendo {info['name']} a GitHub ({len(snap['wip_files'])} archivos con cambios)…")
        try:
            git(repo, "push", "origin", f"{snap['commit']}:refs/heads/{branch}", timeout=600)
            remote_sha = git(repo, "ls-remote", "origin", f"refs/heads/{branch}").split()[0]
        except Exception as exc:
            row["estado"] = f"ERROR: no se pudo subir a GitHub ({exc})"
            continue
        git(repo, "update-ref", f"refs/heads/{branch}", snap["commit"])
        if remote_sha != snap["commit"]:
            row["estado"] = f"ERROR: GitHub tiene {remote_sha[:12]} en vez de {snap['commit'][:12]}"
            continue
        record = {"kind": "ir", "at": stamp, "src": src, "dest": dest_name, "repo": info["path"],
                  "name": info["name"], "branch": branch, "commit": snap["commit"], "tree": snap["tree"],
                  "base": snap["base"], "dest_bridge": dest_bridge, "dest_workspace": work,
                  "message_sha256": hashlib.sha256(msg.encode()).hexdigest(), "phase": "github"}
        state["relevos"].append(record)
        save_state(state)
        pending.append((row, info, snap, on_dest, work, prep, msg, record))

    # Todo el código ya está a salvo en GitHub. Desde acá trabaja el destino.
    if pending:
        log(f"Código a salvo en GitHub. Preparando {len(pending)} proyecto(s) en {dest_name}…")
    for row, info, snap, on_dest, work, prep, msg, record in pending:
        prep_ws = f"{dest['projects_root']}/{info['name']}" if on_dest else dest.get("landing_workspace") or dest["projects_root"]
        try:
            prep_s = http("POST", dest_bridge + "/sessions", {
                "title": f"Relevo {info['name']}: preparación"[:120], "workspace_path": prep_ws}, socks5=socks)
            http("POST", dest_bridge + "/message", {"message": prep, "session_id": prep_s["id"],
                 "workspace_path": prep_ws, "codex_options": FULL_ACCESS}, socks5=socks, timeout=60)
        except Exception as exc:
            row["estado"] = f"ERROR: código a salvo en GitHub ({branch}); no pude pedir la preparación en {dest_name} ({exc})"
            continue
        record.update(prep_session=prep_s["id"], phase="preparando")
        row["chat_preparacion"] = prep_s["id"]
    save_state(state)
    for row, info, snap, on_dest, work, prep, msg, record in pending:
        if record.get("phase") != "preparando":
            continue
        reply = wait_reply(dest_bridge, record["prep_session"], socks, args.esperar_destino)
        m = re.search(r"RELEVO_LISTO\s+(\S+)\s+([0-9a-f]{40})", reply)
        if not m or m.group(2) != snap["commit"]:
            fail = re.search(r"RELEVO_FALLO\s+(.+)", reply)
            row["estado"] = ("ERROR: preparación en " + dest_name + " no confirmó el hash: " +
                             (fail.group(1)[:200] if fail else (reply[-200:] or "sin respuesta a tiempo")) +
                             " (código a salvo en GitHub)")
            continue
        try:
            session = http("POST", dest_bridge + "/sessions", {
                "title": f"Relevo {info['name']} desde {src}"[:120], "workspace_path": work}, socks5=socks)
            accepted = http("POST", dest_bridge + "/message", {
                "message": msg, "session_id": session["id"], "workspace_path": work}, socks5=socks, timeout=60)
        except Exception as exc:
            row["estado"] = f"ERROR: preparado en {work}, pero no pude abrir el chat de continuación ({exc})"
            continue
        row.update(estado=f"en {dest_name}: código verificado ({snap['commit'][:12]}) y chat de continuación abierto",
                   chat_destino=session["id"], job_destino=accepted.get("job_id"))
        record.update(dest_session=session["id"], phase="listo")
        save_state(state)
    for row, name, chats in context_only:
        ws = f"{dest['projects_root']}/{name}"
        ws = ws if ws in dest_ws else dest.get("landing_workspace") or dest["projects_root"]
        body = (f"RELEVO desde {src}: Bruno sigue acá la conversación de **{name}**. "
                f"El código y los cambios sin commit de este proyecto QUEDARON EN {src} (no se subieron: {row['estado']}). "
                "No asumas que esta carpeta tiene esos cambios. Respondé en 2 líneas qué tenés disponible acá "
                "y esperá instrucciones de Bruno.\n\n## Contexto de los chats\n")
        for c in chats:
            if len(body) + len(c) > 9500:
                body += "\n(…contexto recortado por tamaño)"
                break
            body += c + "\n\n"
        try:
            sess = http("POST", dest_bridge + "/sessions", {"title": f"Relevo {name} desde {src} (sólo contexto)"[:120],
                        "workspace_path": ws}, socks5=socks)
            http("POST", dest_bridge + "/message", {"message": body, "session_id": sess["id"],
                 "workspace_path": ws}, socks5=socks, timeout=60)
            row["chat_destino"] = sess["id"]
            row["estado"] += f"; chats cerrados y continuación abierta en {dest_name} sólo con contexto"
        except Exception as exc:
            row["estado"] += f"; no pude abrir la continuación en {dest_name} ({exc})"
    log("Relevo terminado.")
    print(json.dumps({"relevo": f"{src}->{dest_name}", "rama": branch, "proyectos": report},
                     ensure_ascii=False, indent=2))
    return 0 if all(not r["estado"].startswith("ERROR") for r in report) else 1


# --------------------------------------------------------------- volver/traer
def fetch_back(repo: Path, dest_name: str, since_branch: str | None) -> list[dict]:
    refs = git(repo, "ls-remote", "origin", f"refs/heads/relevo/{dest_name}-*").splitlines()
    got = []
    for line in refs:
        sha, ref = line.split()
        name = ref.removeprefix("refs/heads/")
        if since_branch and name.split("-", 1)[-1] < since_branch.split("-", 1)[-1]:
            continue
        git(repo, "fetch", "origin", f"+{ref}:refs/heads/{name}", timeout=600)
        local = git(repo, "rev-parse", f"refs/heads/{name}")
        base = since_branch and git(repo, "rev-parse", "--verify", f"refs/heads/{since_branch}", check=False)
        stat = git(repo, "diff", "--shortstat", f"{base}..{name}", check=False) if base else ""
        got.append({"rama": name, "commit": local, "verificado": local == sha, "cambios": stat})
    return got


def cmd_volver(args) -> int:
    hosts = load_hosts()
    src = self_host(hosts)
    state = load_state()
    dest = hosts[args.destino]
    out = []
    latest: dict[str, dict] = {}
    for r in state["relevos"]:
        if r["dest"] == args.destino and r.get("kind") == "ir" and r.get("phase") == "listo":
            latest[r["repo"]] = r
    for repo, r in latest.items():
        if args.proyecto and Path(repo) not in {Path(p).resolve() for p in args.proyecto}:
            continue
        row = {"proyecto": repo, "relevo": r["branch"]}
        before = {l.split()[1] for l in git(Path(repo), "ls-remote", "origin",
                                            f"refs/heads/relevo/{args.destino}-*").splitlines()}
        if args.pedir:
            http("POST", r["dest_bridge"] + "/message", {
                "message": (f"Volvemos a {src}. En tu ruta de trabajo de este relevo: guardá todo el WIP "
                            f"(git add -A sin secretos), commit y `git push origin HEAD:refs/heads/relevo/{args.destino}-{now_stamp()}`. "
                            "Frená lo que estés haciendo en un punto seguro. Respondé con rama y hash. Sin merge."),
                "session_id": r["dest_session"], "workspace_path": r["dest_workspace"],
                "codex_options": FULL_ACCESS},
                socks5=dest.get("socks5"), timeout=60)
            deadline = time.time() + args.esperar
            while time.time() < deadline:
                now = {l.split()[1] for l in git(Path(repo), "ls-remote", "origin",
                                                 f"refs/heads/relevo/{args.destino}-*").splitlines()}
                if now - before:
                    break
                time.sleep(10)
            else:
                row["estado"] = f"{args.destino} no subió una rama nueva en {args.esperar}s; reintentá con `traer`"
        row["traido"] = fetch_back(Path(repo), args.destino, r["branch"])
        row.setdefault("estado", "traído como rama aparte (sin merge)" if row["traido"] else "nada para traer")
        state["relevos"].append({"kind": "volver", "at": now_stamp(), "src": args.destino, "dest": src,
                                 "repo": repo, "branches": [t["rama"] for t in row["traido"]]})
        out.append(row)
    save_state(state)
    print(json.dumps({"vuelta": f"{args.destino}->{src}", "proyectos": out}, ensure_ascii=False, indent=2))
    return 0


def cmd_estado(_args) -> int:
    print(json.dumps(load_state(), ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    ir = sub.add_parser("ir", help="pasar el trabajo a otro equipo")
    ir.add_argument("destino")
    ir.add_argument("--proyecto", action="append")
    ir.add_argument("--horas", type=float, default=12, help="chats tocados en las últimas N horas")
    ir.add_argument("--esperar", type=int, default=180,
                    help="segundos para que los agentes activos cierren solos tras el steering")
    ir.add_argument("--esperar-destino", type=int, default=420, help="segundos para que el destino prepare")
    ir.add_argument("--simular", action="store_true")
    ir.add_argument("--forzar", action="store_true")
    ir.add_argument("--permitir-publico", action="store_true")
    ir.add_argument("--todo", action="store_true",
                    help="modo sistema (botón de la app): cierra todos los chats activos, sin excluir al disparador")
    ir.set_defaults(func=cmd_ir)
    for name, pedir in (("volver", True), ("traer", False)):
        v = sub.add_parser(name)
        v.add_argument("destino")
        v.add_argument("--proyecto", action="append")
        v.add_argument("--esperar", type=int, default=600)
        v.set_defaults(func=cmd_volver, pedir=pedir)
    sub.add_parser("estado").set_defaults(func=cmd_estado)
    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
