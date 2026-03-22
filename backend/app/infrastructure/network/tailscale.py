from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass


@dataclass(slots=True)
class TailscaleInfo:
    installed: bool
    online: bool
    tailnet_name: str | None = None
    device_name: str | None = None
    magic_dns_name: str | None = None
    ipv4: str | None = None

    @property
    def suggested_url(self) -> str | None:
        target = self.magic_dns_name or self.ipv4
        if not target:
            return None
        return f"http://{target}:8000"


def detect_tailscale_info(socket_path: str | None = None) -> TailscaleInfo:
    command = ["tailscale"]
    if socket_path:
        command.append(f"--socket={socket_path}")
    command.extend(["status", "--json"])

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except FileNotFoundError:
        return TailscaleInfo(installed=False, online=False)
    except Exception:
        return TailscaleInfo(installed=True, online=False)

    if result.returncode != 0:
        return TailscaleInfo(installed=True, online=False)

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return TailscaleInfo(installed=True, online=False)

    self_info = payload.get("Self") or {}
    current_tailnet = payload.get("CurrentTailnet") or {}
    dns_name = self_info.get("DNSName")
    magic_dns_name = dns_name.rstrip(".") if isinstance(dns_name, str) else None
    ips = self_info.get("TailscaleIPs") or []
    ipv4 = next((ip for ip in ips if "." in ip), None)

    return TailscaleInfo(
        installed=True,
        online=bool(payload.get("BackendState") == "Running" and (magic_dns_name or ipv4)),
        tailnet_name=current_tailnet.get("Name"),
        device_name=self_info.get("HostName"),
        magic_dns_name=magic_dns_name,
        ipv4=ipv4,
    )
