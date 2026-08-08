from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from backend.app.application.services.project_scaffold_service import (
    ProjectScaffoldService,
    ScaffoldDraftInput,
    ScaffoldError,
    _owned_generated_files,
    _scan_forbidden_product_content,
    _redact,
    _scan_generated_secrets,
    _unsafe_provider_command,
)
from backend.app.domain.entities.project_scaffold import CloudflareMode


def _service(tmp_path: Path) -> ProjectScaffoldService:
    projects = tmp_path / "projects"
    projects.mkdir()
    return ProjectScaffoldService(
        projects_root=projects,
        state_root=tmp_path / "state",
        execute_commands=False,
        allow_remote_writes=False,
    )


@pytest.mark.parametrize("slug", ("../escape", "/absolute", "bad_slug", "a/../b"))
def test_scaffold_rejects_path_traversal_slugs(tmp_path: Path, slug: str) -> None:
    with pytest.raises(ScaffoldError, match="Invalid scaffold slug"):
        _service(tmp_path).create_draft(ScaffoldDraftInput(name="Safe", slug=slug))


def test_provider_command_policy_rejects_shell_apply_and_traversal() -> None:
    assert _unsafe_provider_command(("bash", "-c", "echo unsafe"))
    assert _unsafe_provider_command(("terraform", "apply"))
    assert _unsafe_provider_command(("npm", "ci", "../other"))
    assert _unsafe_provider_command(("npm", "ci", "/tmp/outside-workspace"))
    assert _unsafe_provider_command(
        ("terraform", "-chdir=infra/aws", "apply", "-auto-approve")
    )
    assert _unsafe_provider_command(("npm", "ci", "--ignore-scripts")) is None


def test_generated_file_conflict_is_preserved_and_reported(tmp_path: Path) -> None:
    service = _service(tmp_path)
    draft = service.create_draft(
        ScaffoldDraftInput(
            name="Conflict",
            github_mode="disabled",
            cloudflare_mode=CloudflareMode.DISABLED,
        )
    )
    service.confirm_draft(draft.id, draft.contract_hash)
    job = service.start_or_resume(draft.id)
    manifest = Path(job.workspace_path) / ".codex/project.yaml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        yaml.safe_dump(draft.manifest, sort_keys=False),
        encoding="utf-8",
    )
    mobile = Path(job.workspace_path) / "apps/mobile/app/index.tsx"
    mobile.parent.mkdir(parents=True)
    mobile.write_text("user-owned\n", encoding="utf-8")

    completed = service.run(job.id)

    assert mobile.read_text(encoding="utf-8") == "user-owned\n"
    assert any(
        item["code"] == "generated_file_conflict"
        for item in completed.to_payload()["blockers"]
    )


def test_secret_scan_and_redaction_do_not_persist_values(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "config.ts").write_text(
        'const apiKey = "live-dangerous-value";\n', encoding="utf-8"
    )

    assert _scan_generated_secrets(workspace) == ["config.ts"]
    assert "live-dangerous-value" not in _redact(
        "api_key=live-dangerous-value"
    )
    assert "0123456789abcdef" not in _redact("account_id=0123456789abcdef")
    assert "Bearer-sensitive" not in _redact(
        "Authorization: Bearer-sensitive"
    )


def test_generated_ownership_excludes_dependency_and_build_trees(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "apps/mobile/node_modules/pkg").mkdir(parents=True)
    (workspace / "apps/mobile/android/app/src").mkdir(parents=True)
    (workspace / "apps/mobile/build").mkdir(parents=True)
    (workspace / "apps/mobile/package-lock.json").write_text("{}")
    (workspace / "apps/mobile/node_modules/pkg/index.js").write_text("x")
    (workspace / "apps/mobile/android/app/src/Main.kt").write_text("class Main")
    (workspace / "apps/mobile/build/app.apk").write_bytes(b"apk")

    owned = _owned_generated_files(workspace, set())

    assert owned == {
        "apps/mobile/android/app/src/Main.kt",
        "apps/mobile/package-lock.json",
    }


def test_security_scans_ignore_installed_dependencies_but_scan_authored_source(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    dependency = workspace / "apps/web/node_modules/pkg/index.js"
    dependency.parent.mkdir(parents=True)
    dependency.write_text(
        'const password = "dependency-secret-value"; // auth dashboard',
        encoding="utf-8",
    )

    assert _scan_generated_secrets(workspace) == []
    assert _scan_forbidden_product_content(workspace) == []

    source = workspace / "apps/web/src/product.ts"
    source.parent.mkdir(parents=True)
    source.write_text(
        'const auth = true; const password = "authored-secret-value";',
        encoding="utf-8",
    )

    assert _scan_generated_secrets(workspace) == ["apps/web/src/product.ts"]
    assert _scan_forbidden_product_content(workspace) == [
        "apps/web/src/product.ts:auth"
    ]


def test_forbidden_content_scan_avoids_generated_tooling_substring_false_positives(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    gradlew = workspace / "apps/mobile/android/gradlew"
    settings = workspace / "apps/mobile/android/settings.gradle"
    compiled = workspace / "apps/web/.svelte-kit/output/server/index.js"
    gradlew.parent.mkdir(parents=True)
    settings.parent.mkdir(parents=True, exist_ok=True)
    compiled.parent.mkdir(parents=True)
    gradlew.write_text("Copyright the original authors.\n", encoding="utf-8")
    settings.write_text("dependencyResolutionManagement { versionCatalogs {} }\n")
    compiled.write_text("const authorization = 'framework internals';\n")

    assert _scan_forbidden_product_content(workspace) == []
