#!/usr/bin/env python3
"""Install the isolated notification companions without restarting chat backends."""

from pathlib import Path
import argparse
import json
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workspace",
        type=Path,
        required=True,
        help="Real host workspace owning Secrets and chat databases",
    )
    parser.add_argument("--node", required=True)
    parser.add_argument("--python", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1]
    host = args.workspace.resolve()
    # Public paths only; secret values stay behind the Secrets panel file.
    databases = {
        "prod": host / ".data/chat_store.sqlite3",
        "dev": host / ".run/dev-backend-8118/data/chat_store.sqlite3",
    }
    for environment, database in databases.items():
        if not database.is_file():
            raise SystemExit(
                f"The existing {environment} database was not found; no service changed."
            )
    if (
        not (host / ".env").is_file()
        or not Path(args.node).is_file()
        or not Path(args.python).is_file()
    ):
        raise SystemExit("Secrets file, Python and Node must exist.")
    unit_root = Path.home() / ".config/systemd/user"
    services = []
    for environment, port in [("prod", 8125), ("dev", 8126)]:
        name = f"codex-mobile-push-{environment}.service"
        command = [
            args.python,
            "-m",
            "backend.app.push_server",
            "--environment",
            environment,
            "--database",
            str(databases[environment]),
            "--secrets-file",
            str(host / ".env"),
            "--node",
            args.node,
            "--port",
            str(port),
        ]
        body = "\n".join(
            [
                "[Unit]",
                f"Description=Codex Mobile {environment} push notifications",
                "After=network-online.target",
                "[Service]",
                f"WorkingDirectory={source}",
                "ExecStart=" + " ".join(json.dumps(a) for a in command),
                "Restart=on-failure",
                "RestartSec=5",
                "KillMode=control-group",
                "UMask=0077",
                "[Install]",
                "WantedBy=default.target",
                "",
            ]
        )
        if args.apply:
            unit_root.mkdir(parents=True, exist_ok=True)
            (unit_root / name).write_text(body)
        services.append(name)
    if args.apply:
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(
            ["systemctl", "--user", "enable", *services], check=True
        )
        subprocess.run(["systemctl", "--user", "restart", *services], check=True)
    print(
        json.dumps(
            {
                "services": services,
                "applied": args.apply,
                "chatBackendsRestarted": False,
                "source": str(source),
            }
        )
    )


if __name__ == "__main__":
    main()
