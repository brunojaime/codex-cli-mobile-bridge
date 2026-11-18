"""Probe real meeting sandbox access without starting a model turn or chat."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import select
import shlex
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from backend.app.application.services.meeting_intake_service import analysis_options


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    project = args.project.resolve(strict=True)
    load_dotenv(ROOT / ".env", override=False)
    command = shlex.split(os.environ.get("CODEX_COMMAND", "codex"))
    for override in analysis_options().config_overrides:
        command += ["-c", override]
    command += ["app-server", "--listen", "stdio://"]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True)

    def rpc(ident, method, params):
        process.stdin.write(json.dumps({"id": ident, "method": method, "params": params}) + "\n")
        process.stdin.flush()
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            if not select.select([process.stdout], [], [], max(0, deadline - time.monotonic()))[0]:
                break
            line = process.stdout.readline()
            if not line:
                raise RuntimeError("app_server_closed")
            response = json.loads(line)
            if response.get("id") == ident:
                if "error" in response:
                    raise RuntimeError(str(response["error"]))
                return response["result"]
        raise TimeoutError("app_server_probe_timeout")

    # No thread/start or turn/start: this executes only a deterministic probe.
    probe = r'''
from pathlib import Path
import json, socket, uuid
root = Path.cwd()
readable = []
for name in ["README.md", "AGENTS.md", "codex-bridge.yaml", "docs/HANDOFF.md"]:
    p = root / name
    if p.is_file():
        with p.open("rb") as source:
            source.read(256)
        readable.append(name)
code_roots = [root / n for n in ["src", "backend", "apps", "lib", "services"] if (root / n).is_dir()]
code_file = next((p for directory in code_roots for p in directory.rglob("*")
                  if p.is_file() and p.suffix in {".ts", ".tsx", ".py", ".dart", ".js"}
                  and "node_modules" not in p.parts), None)
if code_file:
    with code_file.open("rb") as source:
        source.read(256)
    readable.append(str(code_file.relative_to(root)))
target = root / (".meeting-access-probe-" + uuid.uuid4().hex)
write_denied = False
try:
    target.write_text("probe")
except OSError:
    write_denied = True
finally:
    if target.exists():
        target.unlink()
network_denied = False
try:
    with socket.create_connection(("127.0.0.1", 8000), timeout=2):
        pass
except PermissionError:
    network_denied = True
except OSError as error:
    network_denied = error.errno in {1, 13, 101}
print(json.dumps({"readable_files": readable, "code_readable": code_file is not None,
                  "write_denied": write_denied, "network_denied": network_denied}))
'''
    try:
        rpc(1, "initialize", {"clientInfo": {"name": "meeting-access-check", "version": "1.0"}})
        process.stdin.write('{"method":"initialized"}\n')
        process.stdin.flush()
        result = rpc(2, "command/exec", {"command": [sys.executable, "-c", probe],
                     "cwd": str(project), "sandboxPolicy": {"type": "readOnly"}, "timeoutMs": 15000})
        if result["exitCode"] != 0:
            raise RuntimeError(result.get("stderr", "sandbox_probe_failed"))
        facts = json.loads(result["stdout"])
        facts.update(project=project.name, model_turn_started=False)
        if not (facts["readable_files"] and facts["code_readable"] and facts["write_denied"] and facts["network_denied"]):
            raise RuntimeError(json.dumps(facts))
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(facts, indent=2) + "\n")
        print(json.dumps(facts))
    finally:
        process.terminate()
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()


if __name__ == "__main__":
    main()
