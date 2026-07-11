from __future__ import annotations

import shutil
import subprocess

import pytest


def test_cloudflare_email_endpoint_worker_validation() -> None:
    if shutil.which("node") is None:
        pytest.skip("node is required for the Cloudflare email endpoint harness")
    completed = subprocess.run(
        ["scripts/validate_cloudflare_email_endpoint.sh"],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "cloudflare email endpoint validation completed" in completed.stdout
