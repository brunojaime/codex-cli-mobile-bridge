import importlib.util
import subprocess
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "relevo", Path(__file__).resolve().parents[1] / "scripts" / "relevo.py"
)
relevo = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(relevo)


def sh(cwd, *args):
    return subprocess.run(args, cwd=cwd, check=True, text=True, capture_output=True).stdout.strip()


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "app"
    repo.mkdir()
    sh(repo, "git", "init", "-q", "-b", "main")
    sh(repo, "git", "config", "user.name", "t")
    sh(repo, "git", "config", "user.email", "t@example.invalid")
    (repo / ".gitignore").write_text("node_modules/\n")
    (repo / "a.txt").write_text("base\n")
    sh(repo, "git", "add", "-A")
    sh(repo, "git", "commit", "-qm", "base")
    sh(repo, "git", "remote", "add", "origin", "https://github.com/x/app-real.git")
    return repo


def test_snapshot_keeps_local_state_and_excludes_secrets(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "a.txt").write_text("base\nwip\n")
    (repo / "nuevo.txt").write_text("nuevo\n")
    (repo / "staged.txt").write_text("staged\n")
    sh(repo, "git", "add", "staged.txt")
    (repo / ".env").write_text("TOKEN=valor\n")  # no ignorado: igual debe excluirse
    (repo / ".dev.vars").write_text("K=v\n")
    (repo / ".env.example").write_text("TOKEN=\n")
    nested = repo / "anidado"
    nested.mkdir()
    sh(nested, "git", "init", "-q")
    sh(nested, "git", "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-q", "--allow-empty", "-m", "x")
    before_status = sh(repo, "git", "status", "--porcelain")
    before_head = sh(repo, "git", "rev-parse", "HEAD")

    snap = relevo.snapshot(repo, "t", "lenovo")

    assert sh(repo, "git", "status", "--porcelain") == before_status
    assert sh(repo, "git", "rev-parse", "HEAD") == before_head
    files = set(sh(repo, "git", "ls-tree", "-r", "--name-only", snap["commit"]).splitlines())
    assert {"a.txt", "nuevo.txt", "staged.txt", ".env.example"} <= files
    assert ".env" not in files and ".dev.vars" not in files and "anidado" not in files
    assert sh(repo, "git", "show", f"{snap['commit']}:a.txt") == "base\nwip"
    assert any("anidado" in e for e in snap["excluded"])
    # repetir sin cambios produce el mismo árbol
    assert relevo.snapshot(repo, "t2", "lenovo")["tree"] == snap["tree"]


def test_clean_repo_reuses_head(tmp_path):
    repo = make_repo(tmp_path)
    snap = relevo.snapshot(repo, "t", "lenovo")
    assert snap["commit"] == sh(repo, "git", "rev-parse", "HEAD")


def test_secret_inventory_lists_names_without_values(tmp_path):
    repo = make_repo(tmp_path)
    (repo / ".gitignore").write_text(".env\n")
    (repo / ".env").write_text("export API_TOKEN=supersecreto\nOTRO=x\n")
    inv = relevo.secret_inventory(repo)
    assert inv == [{"file": ".env", "keys": ["API_TOKEN", "OTRO"]}]
    assert "supersecreto" not in repr(inv)


def test_repo_name_from_remote_and_redaction(tmp_path):
    repo = make_repo(tmp_path)
    info = relevo.repo_info(repo)
    assert info["name"] == "app-real" and info["local_name"] == "app"
    assert "hunter2" not in relevo.redact("la password: hunter2 y token=abcd1234")
    assert relevo.is_secret_path("src/.env.local") and not relevo.is_secret_path(".env.example")


def test_messages_fit_bridge_limit(tmp_path):
    repo = make_repo(tmp_path)
    info = relevo.repo_info(repo)
    snap = relevo.snapshot(repo, "t", "lenovo")
    dest = {"projects_root": "/home/batata/Projects"}
    chats = ["### chat\n" + "- x " * 3000] * 3
    msg = relevo.context_message(info, snap, "relevo/lenovo-1", "batata", "lenovo",
                                 "/home/batata/Projects/app-real", chats, [], [])
    assert len(msg) <= 10000
    prep = relevo.prep_message(info, snap, "relevo/lenovo-1", dest, "lenovo", on_dest=True)
    assert snap["commit"] in prep and "app-real-relevo" in prep and "FETCH_HEAD" in prep


def _session(sid, active, content=""):
    stages = [{"job_id": "job-" + sid, "job_status": "running" if active else "completed"}]
    return {"id": sid, "current_run": {"is_active": active, "stages": stages},
            "messages": [{"role": "assistant", "content": content}]}


def test_close_sessions_steering_then_summary(monkeypatch):
    calls, polls = [], {"n": 0}

    def fake_http(method, url, body=None, socks5=None, timeout=30):
        calls.append((method, url, body))
        if url.endswith("/steer"):
            assert "NO ejecutes `relevo`" in body["message"]
            return {"steered": True}
        polls["n"] += 1
        return _session("a", False, "listo\nRELEVO_CIERRE\nObjetivo: x\nPendiente: y")

    monkeypatch.setattr(relevo, "http", fake_http)
    out = relevo.close_sessions([("http://b", _session("a", True))], wait_s=5, poll_s=0)
    assert out["a"]["via"] == "cerró por steering"
    assert out["a"]["summary"].startswith("Objetivo: x")
    assert not any(u.endswith("/cancel") for _, u, _ in calls)


def test_close_sessions_fallback_cancels_only_after_wait(monkeypatch):
    calls = []

    def fake_http(method, url, body=None, socks5=None, timeout=30):
        calls.append(url)
        if url.endswith("/steer"):
            raise RuntimeError("HTTP 409 This job cannot be redirected while it runs.")
        if url.endswith("/cancel") or url.endswith("/message"):
            return {}
        return _session("b", True)

    monkeypatch.setattr(relevo, "http", fake_http)
    out = relevo.close_sessions([("http://b", _session("b", True)), ("http://b", _session("c", False))],
                                wait_s=0, poll_s=0)
    assert out["b"]["via"].startswith("cancelado tras espera (steering no disponible")
    assert out["c"]["via"] == "inactivo"
    assert calls.index("http://b/jobs/job-b/cancel") > calls.index("http://b/message") > calls.index("http://b/jobs/job-b/steer")
    assert not any("job-c" in u for u in calls)


def test_close_sessions_queues_close_when_steering_rejected(monkeypatch):
    state = {"queued": False}

    def fake_http(method, url, body=None, socks5=None, timeout=30):
        if url.endswith("/steer"):
            raise RuntimeError("HTTP 409")
        if url.endswith("/message"):
            assert body["session_id"] == "d" and "RELEVO_CIERRE" in body["message"]
            state["queued"] = True
            return {"job_id": "q"}
        return _session("d", False, "RELEVO_CIERRE\nHecho: z") if state["queued"] else _session("d", True)

    monkeypatch.setattr(relevo, "http", fake_http)
    out = relevo.close_sessions([("http://b", _session("d", True))], wait_s=5, poll_s=0)
    assert out["d"]["via"].startswith("cerró con mensaje de cierre encolado")
    assert out["d"]["summary"] == "Hecho: z"
