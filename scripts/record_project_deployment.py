#!/usr/bin/env python3
"""Append a real deploy receipt after a project's publisher has finished.

Run with the bridge Python environment. Does not publish or probe anything.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.application.services.project_deployments import (
    DeploymentRecord,
    record_deployment,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--id", required=True)
    parser.add_argument("--environment", choices=["dev", "qa", "prod"], required=True)
    parser.add_argument(
        "--status",
        choices=["published", "deploying", "failed", "disabled", "expired"],
        required=True,
    )
    parser.add_argument(
        "--deployed-at", default=None, help="ISO-8601 with timezone; defaults to now"
    )
    parser.add_argument("--release")
    parser.add_argument("--commit")
    args = parser.parse_args()
    record_deployment(
        args.project,
        DeploymentRecord(
            id=args.id,
            environment=args.environment,
            status=args.status,
            deployed_at=args.deployed_at or datetime.now(timezone.utc),
            release=args.release,
            commit=args.commit,
        ),
    )
    print("Comprobante de deploy registrado.")


if __name__ == "__main__":
    main()
