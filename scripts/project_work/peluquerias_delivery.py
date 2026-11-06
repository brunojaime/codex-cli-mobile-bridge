"""Fixed DEV-only adapter around Polo's official release-environment workflow.

Project preparation and enabling execution are separate: inspect is read-only;
validate/publish are called by the coordinator only after an accepted cycle.
"""
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    if len(sys.argv) != 3 or sys.argv[2] not in {"inspect", "validate", "deploy"}:
        raise ValueError("Expected operator configuration and inspect/validate/deploy")
    config_path = Path(sys.argv[1]).resolve()
    config = json.loads(config_path.read_text())
    root = Path(config["root"]).resolve()
    node = config["node"]
    environment = dict(os.environ)
    environment.pop("CLOUDFLARE_API_TOKEN", None)
    environment["PATH"] = str(Path(node).parent) + ":" + environment["PATH"]
    environment["NODE_OPTIONS"] = "--dns-result-order=ipv4first --no-network-family-autoselection"
    checker = Path(__file__).with_name("peluquerias_delivery.mjs")
    if sys.argv[2] == "inspect":
        subprocess.run([node, str(checker), str(config_path), "inspect"], cwd=root, env=environment, check=True, timeout=120)
        return
    state = Path(config["state"]).resolve()
    plan = json.loads((state / "current.json").read_text())
    for key in ("evidenceRoot", "privateRoot"):
        path = Path(plan[key]).resolve()
        if path == state or not path.is_relative_to(state) or path.is_relative_to(root):
            raise ValueError("Evidence must remain in private operator custody")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    if plan["revision"] != revision:
        raise ValueError("Evidence belongs to another revision")
    environment["POLO_RELEASE_EVIDENCE"] = plan["evidenceRoot"]
    environment["POLO_RELEASE_PRIVATE"] = plan["privateRoot"]
    if sys.argv[2] == "validate":
        subprocess.run([node, str(checker), str(config_path), "inspect"], cwd=root, env=environment, check=True, timeout=120)
        subprocess.run([node, "scripts/release-environment.mjs", "prepare", "dev"], cwd=root, env=environment, check=True, timeout=700)
    subprocess.run([node, str(checker), str(config_path), sys.argv[2]], cwd=root, env=environment, check=True, timeout=120)
    if sys.argv[2] == "deploy":
        # Arguments are owned by the operator, never supplied in a backlog request.
        subprocess.run([node, "scripts/release-environment.mjs", "publish", "dev"], cwd=root, env=environment, check=True, timeout=850)


if __name__ == "__main__":
    main()
