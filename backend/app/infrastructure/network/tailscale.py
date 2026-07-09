from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(slots=True)
class TailscaleInfo:
    installed: bool
    online: bool
    tailnet_name: str | None = None
    device_name: str | None = None
    magic_dns_name: str | None = None
    ipv4: str | None = None
    serve_base_urls: tuple[str, ...] = ()
    api_port: int = 8000

    @property
    def direct_url(self) -> str | None:
        target = self.magic_dns_name or self.ipv4
        if not target:
            return None
        return f"http://{target}:{self.api_port}"

    @property
    def public_base_urls(self) -> list[str]:
        if self.serve_base_urls:
            return list(self.serve_base_urls)
        direct_url = self.direct_url
        return [direct_url] if direct_url else []

    @property
    def preferred_client_url(self) -> str | None:
        urls = self.public_base_urls
        return urls[0] if urls else None

    @property
    def suggested_url(self) -> str | None:
        return self.preferred_client_url


def detect_tailscale_info(
    socket_path: str | None = None,
    *,
    api_port: int = 8000,
) -> TailscaleInfo:
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
        return TailscaleInfo(installed=False, online=False, api_port=api_port)
    except Exception:
        return TailscaleInfo(installed=True, online=False, api_port=api_port)

    if result.returncode != 0:
        return TailscaleInfo(installed=True, online=False, api_port=api_port)

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return TailscaleInfo(installed=True, online=False, api_port=api_port)

    self_info = payload.get("Self") or {}
    current_tailnet = payload.get("CurrentTailnet") or {}
    dns_name = self_info.get("DNSName")
    magic_dns_name = dns_name.rstrip(".") if isinstance(dns_name, str) else None
    ips = self_info.get("TailscaleIPs") or []
    ipv4 = next((ip for ip in ips if "." in ip), None)

    return TailscaleInfo(
        installed=True,
        online=bool(
            payload.get("BackendState") == "Running" and (magic_dns_name or ipv4)
        ),
        tailnet_name=current_tailnet.get("Name"),
        device_name=self_info.get("HostName"),
        magic_dns_name=magic_dns_name,
        ipv4=ipv4,
        serve_base_urls=_detect_tailscale_serve_base_urls(socket_path),
        api_port=api_port,
    )


def _detect_tailscale_serve_base_urls(
    socket_path: str | None = None,
) -> tuple[str, ...]:
    command = ["tailscale"]
    if socket_path:
        command.append(f"--socket={socket_path}")
    command.extend(["serve", "status", "--json"])

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception:
        return ()

    if result.returncode != 0:
        return ()

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return ()

    web_entries = payload.get("Web")
    if not isinstance(web_entries, dict):
        return ()

    base_urls: list[str] = []
    for host_port, config in web_entries.items():
        if not isinstance(host_port, str) or not isinstance(config, dict):
            continue
        handlers = config.get("Handlers")
        if not isinstance(handlers, dict) or "/" not in handlers:
            continue
        base_url = _serve_host_port_to_url(host_port)
        if base_url and base_url not in base_urls:
            base_urls.append(base_url)
    return tuple(base_urls)


def _serve_host_port_to_url(host_port: str) -> str | None:
    parsed = urlparse(f"//{host_port}")
    if not parsed.hostname:
        return None
    if parsed.port == 443:
        return f"https://{parsed.hostname}"
    if parsed.port in (None, 80):
        return f"http://{parsed.hostname}"
    return f"http://{parsed.hostname}:{parsed.port}"
