from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path

from backend.app.application.services.project_deployments import read_deployment_index

spec = importlib.util.spec_from_file_location(
    "sync_project_deployments",
    Path(__file__).resolve().parents[1] / "scripts/sync_project_deployments.py",
)
sources = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sources)


def project(name, candidates=(), repo=None):
    return {
        "name": name,
        "workspace_path": "/projects/" + name,
        "repo": repo,
        "candidates": list(candidates),
    }


def test_domain_owner_and_business_qa_override_outdated_worker_name():
    p = project(
        "rd-gestion-hse",
        [
            {
                "environment": "prod",
                "origin": "https://app.consultorard.com.ar",
                "worker": "rd-gestion-hse-production",
            },
            {
                "environment": "qa",
                "origin": "https://rd-qa.nienfos.com",
                "worker": None,
            },
        ],
    )
    mapping = sources.map_workers(
        [p],
        [
            {"id": "rd-gestion-hse-prod"},
            {"id": "rd-gestion-hse-staging"},
            {"id": "rd-gestion-hse-dev"},
        ],
        [
            {
                "hostname": "app.consultorard.com.ar",
                "service": "rd-gestion-hse-prod",
                "environment": "production",
            },
            {
                "hostname": "rd-qa.nienfos.com",
                "service": "rd-gestion-hse-staging",
                "environment": "production",
            },
        ],
    )
    assert mapping[p["workspace_path"]] == {
        "prod": "rd-gestion-hse-prod",
        "qa": "rd-gestion-hse-staging",
        "dev": "rd-gestion-hse-dev",
    }


def test_templates_and_branches_do_not_create_deployments():
    p = project(
        "patsa", [{"environment": "prod", "worker": "patsa-prod", "origin": None}]
    )
    assert sources.map_workers([p], [{"id": "patsa-dev"}], [])[p["workspace_path"]] == {
        "dev": "patsa-dev"
    }


def test_worktrees_share_canonical_project_environment_mapping():
    repo = "owner/peluquerias"
    p = project("peluquerias", repo=repo)
    alias = project("peluquerias-older-checkout", repo=repo)
    mapping = sources.map_workers(
        [alias, p],
        [
            {"id": "peluquerias-dev"},
            {"id": "peluquerias-qa"},
            {"id": "peluquerias-prod"},
        ],
        [],
    )
    assert mapping[p["workspace_path"]] == mapping[alias["workspace_path"]]
    assert set(mapping[p["workspace_path"]]) == {"dev", "qa", "prod"}


def test_embedded_app_is_not_a_bridge_deployment():
    p = project(
        "codex-cli-mobile-bridge",
        [
            {
                "environment": None,
                "worker": "ceredt-static-preview",
                "origin": None,
                "source": "extraordinary/ceredt/wrangler.json",
            }
        ],
    )
    assert (
        sources.map_workers([p], [{"id": "ceredt-static-preview"}], [])[
            p["workspace_path"]
        ]
        == {}
    )


def test_old_preview_is_qa_when_its_actual_domain_is_qa():
    p = project(
        "nienfos-gestion",
        [
            {
                "environment": "preview",
                "worker": "nienfos-gestion-preview",
                "origin": "https://preview.gestion.nienfos.com",
            }
        ],
    )
    mapping = sources.map_workers(
        [p],
        [{"id": "nienfos-gestion-preview"}],
        [
            {
                "hostname": "qa.gestion.nienfos.com",
                "service": "nienfos-gestion-preview",
                "environment": "production",
            }
        ],
    )
    assert mapping[p["workspace_path"]] == {"qa": "nienfos-gestion-preview"}


def test_index_staleness_and_corruption_are_visible(tmp_path):
    file = tmp_path / "index.json"
    file.write_text(
        json.dumps(
            {
                "version": 1,
                "observed_at": (
                    datetime.now(timezone.utc) - timedelta(hours=2)
                ).isoformat(),
                "projects": [],
            }
        )
    )
    assert read_deployment_index(file)[1]
    file.write_text("{private malformed data")
    projects, errors = read_deployment_index(file)
    assert projects == {} and errors
    assert "private" not in str(errors)
