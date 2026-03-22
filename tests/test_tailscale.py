from __future__ import annotations

from unittest.mock import patch

from backend.app.infrastructure.network.tailscale import detect_tailscale_info


def test_detect_tailscale_info_when_not_installed() -> None:
    with patch("subprocess.run", side_effect=FileNotFoundError):
        info = detect_tailscale_info()

    assert info.installed is False
    assert info.online is False
    assert info.suggested_url is None


def test_detect_tailscale_info_when_online() -> None:
    class Completed:
        returncode = 0
        stdout = (
            '{"BackendState":"Running","CurrentTailnet":{"Name":"example-tailnet"},'
            '"Self":{"HostName":"personal","DNSName":"personal.example.ts.net.",'
            '"TailscaleIPs":["100.64.0.10"]}}'
        )

    with patch("subprocess.run", return_value=Completed()):
        info = detect_tailscale_info()

    assert info.installed is True
    assert info.online is True
    assert info.magic_dns_name == "personal.example.ts.net"
    assert info.ipv4 == "100.64.0.10"
    assert info.suggested_url == "http://personal.example.ts.net:8000"


def test_detect_tailscale_info_uses_custom_socket() -> None:
    class Completed:
        returncode = 1
        stdout = ""

    with patch("subprocess.run", return_value=Completed()) as run_mock:
        detect_tailscale_info("/tmp/custom.sock")

    command = run_mock.call_args.args[0]
    assert command[0] == "tailscale"
    assert command[1] == "--socket=/tmp/custom.sock"
