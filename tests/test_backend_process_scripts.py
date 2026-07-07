from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_backend_pid_check_rejects_unrelated_live_process() -> None:
    script = """
      set -euo pipefail
      source scripts/backend_process_lib.sh
      if backend_is_expected_process "$PWD" "$$"; then
        echo "current shell was incorrectly accepted as backend" >&2
        exit 1
      fi
      echo ok
    """

    result = subprocess.run(
        ["bash", "-c", script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "ok"
