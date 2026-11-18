#!/usr/bin/env python3
"""Local operator/agent interface to the same ledger used by the DEV bridge."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.application.services.pipeline_quality_service import (
    PipelineQualityService,
    QualityError,
)
from backend.app.application.services.jev_advisor import JevAdvisor
from backend.app.infrastructure.config.settings import Settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database")
    parser.add_argument("--projects-root")
    parser.add_argument(
        "--jev",
        action="store_true",
        help="Enable bounded OpenRouter advice using Secrets; sends minimized acceptance facts or redacted diagnostic excerpts",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    register = sub.add_parser("register")
    register.add_argument("--workspace", required=True)
    register.add_argument("--work-item", required=True)
    register.add_argument("--stage-id")
    for name in (
        "status",
        "run",
        "diagnose",
        "lessons",
        "learn",
        "gestion-pack",
        "close",
    ):
        command = sub.add_parser(name)
        command.add_argument("packet_id")
        if name == "run":
            command.add_argument("--attempt", required=True)
            command.add_argument("--check", action="append")
        if name == "learn":
            command.add_argument(
                "--file",
                required=True,
                help="JSON with receipt IDs, symptom, cause_hypothesis, resolution, conditions",
            )
        if name == "gestion-pack":
            command.add_argument(
                "--project-id", required=True, help="Canonical project ID from Gestión"
            )
    export = sub.add_parser("export")
    export.add_argument("--after", type=int, default=0)
    feedback_list = sub.add_parser("feedback-list")
    feedback_list.add_argument("--workspace", required=True)
    requirement = sub.add_parser("register-requirement")
    requirement.add_argument("--workspace", required=True)
    requirement.add_argument("--file", required=True)
    requirements = sub.add_parser("requirements")
    requirements.add_argument("--workspace", required=True)
    sources = sub.add_parser("sources")
    sources.add_argument("--workspace", required=True)
    history = sub.add_parser("request-history")
    history.add_argument("id")
    for name in ("requirement-from-source", "revise-requirement", "manual-review"):
        command = sub.add_parser(name)
        command.add_argument("id")
        command.add_argument("--file", required=True)
    for name in (
        "feedback-plan",
        "feedback-status",
        "evaluate-feedback",
        "request-plan",
        "request-status",
        "evaluate-request",
    ):
        command = sub.add_parser(name)
        command.add_argument("request_id")
        if name in {"feedback-plan", "request-plan"}:
            command.add_argument("--file", required=True)
    args = parser.parse_args()
    settings = Settings()
    service = PipelineQualityService(
        database_path=args.database or settings.pipeline_quality_database,
        allowed_roots=[
            args.projects_root or settings.projects_root,
            settings.dev_pipeline_runtime_root,
        ],
        advisor=JevAdvisor(
            api_key=settings.open_router_api_key.get_secret_value()
            if settings.open_router_api_key
            else None,
            enabled=args.jev,
            model=settings.pipeline_quality_jev_model,
            timeout=settings.pipeline_quality_jev_timeout_seconds,
        ),
    )
    try:
        match args.command:
            case "request-history":
                result = service.acceptance_history(args.id)
            case "sources":
                result = service.requirement_sources(args.workspace)
            case "requirement-from-source":
                result = service.requirement_from_source(
                    args.id, json.loads(Path(args.file).read_text())
                )
            case "revise-requirement":
                result = service.revise_requirement(
                    args.id, json.loads(Path(args.file).read_text())
                )
            case "manual-review":
                result = service.record_manual_review(
                    args.id, json.loads(Path(args.file).read_text())
                )
            case "register-requirement":
                result = service.register_requirement(
                    workspace=args.workspace,
                    definition=json.loads(Path(args.file).read_text()),
                )
            case "requirements":
                result = service.requirements(args.workspace)
            case "feedback-list":
                result = service.feedback_requests(args.workspace)
            case "feedback-plan" | "request-plan":
                result = service.bind_feedback_plan(
                    args.request_id, json.loads(Path(args.file).read_text())
                )
            case "feedback-status" | "request-status":
                result = service.feedback_verdict(args.request_id)
            case "evaluate-feedback" | "evaluate-request":
                result = service.feedback_verdict(args.request_id, evaluate=True)
            case "register":
                result = service.register_file(
                    workspace=args.workspace,
                    work_item_id=args.work_item,
                    links={"stage_id": args.stage_id} if args.stage_id else {},
                )
            case "run":
                result = service.execute(
                    args.packet_id, attempt_key=args.attempt, check_ids=args.check
                )
            case "status":
                result = service.status(args.packet_id)
            case "diagnose":
                result = service.diagnose(args.packet_id)
            case "lessons":
                result = service.lessons_for(args.packet_id)
            case "learn":
                result = service.save_lesson(
                    packet_id=args.packet_id, **json.loads(Path(args.file).read_text())
                )
            case "export":
                result = service.export(after=args.after)
            case "gestion-pack":
                result = service.gestion_payload(args.packet_id, args.project_id)
            case "close":
                result = service.close(args.packet_id)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        if args.command == "run":
            technical = result.get("quality") or service.status(args.packet_id)
            return (
                0
                if technical["verified"]
                and not service.feedback_packet_blockers(args.packet_id)
                else 2
            )
        if args.command in {"evaluate-feedback", "evaluate-request"}:
            return 0 if result["verified"] else 2
        return 0
    except (QualityError, ValueError):
        print(
            json.dumps(
                {
                    "error": "quality_operation_rejected",
                    "hint": "Check contract, workspace, revision, dependencies and attempt key. No receipt was accepted from external input.",
                }
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
