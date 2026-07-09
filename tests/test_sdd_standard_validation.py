from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

from backend.app.application.services.sdd_standard_service import (
    DEFAULT_STANDARD_ID,
    SddStandardService,
    SddUnknownStandardError,
    parse_simple_yaml,
)
from backend.app.application.services.sdd_validation_service import (
    SddPreflightValidationService,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_STANDARDS = ROOT / "tests/fixtures/sdd_standards"
MISSING_TEMPLATE_STANDARDS = ROOT / "tests/fixtures/sdd_standards_missing_templates"


def test_standard_service_loads_workbench_sdd_v1() -> None:
    service = SddStandardService(standards_root=FIXTURE_STANDARDS)

    standard = service.load(DEFAULT_STANDARD_ID)

    assert standard.id == "workbench-sdd/v1"
    assert standard.version == 1
    assert standard.payload["context_rules"]["required_safety_rules"] == [
        "manifest_first_resolution",
        "baseline_impact_gates",
        "no_broad_read",
        "unknown_version_hard_failure",
    ]
    assert standard.to_payload()["source_path"].endswith(
        "tests/fixtures/sdd_standards/workbench-sdd/v1.yaml"
    )


def test_standard_service_rejects_unknown_standard_version() -> None:
    service = SddStandardService(standards_root=FIXTURE_STANDARDS)

    try:
        service.load("workbench-sdd/v2")
    except SddUnknownStandardError as exc:
        assert "Unsupported SDD standard version 'workbench-sdd/v2'" in str(exc)
    else:
        raise AssertionError("Expected SddUnknownStandardError")


def test_standard_service_accepts_v1_minor_compatible_alias() -> None:
    service = SddStandardService(standards_root=FIXTURE_STANDARDS)

    standard = service.load("workbench-sdd/v1.3")

    assert standard.id == "workbench-sdd/v1"
    assert standard.requested_id == "workbench-sdd/v1.3"
    assert standard.to_payload()["canonical_id"] == "workbench-sdd/v1"
    assert standard.to_payload()["requested_id"] == "workbench-sdd/v1.3"


def test_standard_service_rejects_malformed_or_unknown_family_versions() -> None:
    service = SddStandardService(standards_root=FIXTURE_STANDARDS)

    for standard_id, expected in (
        ("workbench-sdd/v1.beta", "Unsupported SDD standard version"),
        ("other-sdd/v1", "Unknown SDD standard family 'other-sdd'"),
        ("workbench-sdd", "Use 'workbench-sdd/v1' or 'workbench-sdd/v1.x'"),
    ):
        try:
            service.load(standard_id)
        except SddUnknownStandardError as exc:
            assert expected in str(exc)
        else:
            raise AssertionError(f"Expected SddUnknownStandardError for {standard_id}")


def test_llm_resolution_instructions_use_loaded_standard_semantics() -> None:
    service = SddStandardService(standards_root=FIXTURE_STANDARDS)

    instructions = service.llm_resolution_instructions("workbench-sdd/v1.2")

    assert "Requested standard: workbench-sdd/v1.2" in instructions
    assert "Canonical standard: workbench-sdd/v1" in instructions
    assert (
        "backend/app/infrastructure/config/sdd_standards/workbench-sdd/v1.yaml"
        in instructions
    )
    assert "workbench-sdd/v1.x aliases are backward-compatible" in instructions


def test_simple_yaml_parser_handles_inline_lists_and_comments() -> None:
    parsed = parse_simple_yaml(
        """
context_rules:
  excluded_paths: [.git, "build:cache", 'tmp # literal']
  candidate_limits:
    related_specs: 5
"""
    )

    assert parsed["context_rules"]["excluded_paths"] == [
        ".git",
        "build:cache",
        "tmp # literal",
    ]


def test_preflight_validates_manifest_context_rules_and_scaffold_dry_run(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _write_project(project, standard="workbench-sdd/v1")
    service = SddPreflightValidationService(
        standard_service=SddStandardService(standards_root=FIXTURE_STANDARDS)
    )

    checks = service.validate_workspace(project)
    by_name = {check.name: check for check in checks}

    assert by_name["standard"].status == "pass"
    assert by_name["context_rules"].status == "pass"
    assert (
        "merged candidate_limits related_specs=5 related_diagrams=3"
        in by_name["context_rules"].detail
    )
    assert by_name["template_metadata"].status == "pass"
    assert by_name["scaffold_dry_run"].status == "pass"
    assert "would_create=" in by_name["scaffold_dry_run"].detail
    assert "would_overwrite=0" in by_name["scaffold_dry_run"].detail
    assert not (project / "domain").exists()
    assert not (project / ".sdd").exists()


def test_template_catalog_is_machine_readable() -> None:
    service = SddPreflightValidationService(
        standard_service=SddStandardService(standards_root=FIXTURE_STANDARDS)
    )

    templates = service.list_templates("workbench-sdd/v1")
    by_id = {template.template_id: template for template in templates}

    assert set(by_id) == {
        "constitution",
        "architecture-overview",
        "domain-glossary",
        "data-persistence-model",
    }
    assert by_id["constitution"].destination == ".specify/memory/constitution.md"
    assert by_id["constitution"].source_path.is_file()


def test_preflight_rejects_invalid_context_rules(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_project(
        project,
        standard="workbench-sdd/v1",
        context_rules="""
    context_rules:
      candidate_limits:
        related_specs: 99
      unsupported_key:
        - nope
""",
    )
    service = SddPreflightValidationService(
        standard_service=SddStandardService(standards_root=FIXTURE_STANDARDS)
    )

    checks = service.validate_workspace(project)
    by_name = {check.name: check for check in checks}

    assert by_name["context_rules"].status == "fail"
    assert (
        "Unsupported sdd.context_rules key(s): unsupported_key"
        in by_name["context_rules"].detail
    )
    assert by_name["scaffold_dry_run"].status == "fail"
    assert "Scaffold writes blocked" in by_name["scaffold_dry_run"].detail


def test_sdd_doctor_reports_unknown_standard_version(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_project(project, standard="workbench-sdd/v9")

    result = _run_doctor(project, standards_root=FIXTURE_STANDARDS)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    standard = _check(payload, "standard")
    assert standard["status"] == "fail"
    assert "Unsupported SDD standard version 'workbench-sdd/v9'" in standard["detail"]


def test_sdd_doctor_accepts_compatible_v1_minor_version(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_project(project, standard="workbench-sdd/v1.7")

    result = _run_doctor(project, standards_root=FIXTURE_STANDARDS)

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    standard = _check(payload, "standard")
    assert standard["status"] == "pass"
    assert "Resolved workbench-sdd/v1.7 as workbench-sdd/v1" in standard["detail"]


def test_sdd_doctor_reports_missing_template_metadata(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_project(project, standard="workbench-sdd/v1")

    result = _run_doctor(project, standards_root=MISSING_TEMPLATE_STANDARDS)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    template_metadata = _check(payload, "template_metadata")
    assert template_metadata["status"] == "fail"
    assert "Standard is missing templates metadata" in template_metadata["detail"]


def test_preflight_rejects_malformed_template_metadata(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_project(project, standard="workbench-sdd/v1")
    standards_root = _write_standard_fixture(
        tmp_path / "standards",
        required_artifacts=["domain/glossary.md"],
        malformed_template_metadata=True,
    )
    service = SddPreflightValidationService(
        standard_service=SddStandardService(standards_root=standards_root)
    )

    checks = service.validate_workspace(project)
    by_name = {check.name: check for check in checks}

    assert by_name["template_metadata"].status == "fail"
    assert (
        "Template constitution is missing required metadata: source"
        in by_name["template_metadata"].detail
    )
    assert by_name["scaffold_dry_run"].status == "fail"


def test_governance_checks_pass_with_valid_diagram_metadata(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_project(project, standard="workbench-sdd/v1")
    _write_diagram_metadata(
        project / "architecture/components.yaml",
        diagram_id="components",
        diagram_type="components",
        scope="baseline",
        source="architecture/components.mmd",
        change_policy="baseline_impact_required",
    )
    _write_diagram_metadata(
        project / "specs/001-demo/diagrams/sequence.yaml",
        diagram_id="sequence",
        diagram_type="sequence",
        scope="feature",
        source="specs/001-demo/diagrams/sequence.mmd",
    )
    service = SddPreflightValidationService(
        standard_service=SddStandardService(standards_root=FIXTURE_STANDARDS)
    )

    checks = service.validate_workspace(project)
    by_name = {check.name: check for check in checks}

    assert by_name["taxonomy_governance"].status == "pass"
    assert by_name["artifact_governance"].status == "pass"
    assert by_name["diagram_metadata"].status == "pass"
    assert by_name["mermaid_validation"].status == "pass"
    assert "render validation skipped" in by_name["mermaid_validation"].detail


def test_taxonomy_rejects_unsupported_template_artifact_type(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_project(project, standard="workbench-sdd/v1")
    standards_root = _write_standard_fixture(
        tmp_path / "standards",
        required_artifacts=["domain/glossary.md"],
        invalid_template_artifact_type=True,
    )
    service = SddPreflightValidationService(
        standard_service=SddStandardService(standards_root=standards_root)
    )

    checks = service.validate_workspace(project)
    taxonomy = {check.name: check for check in checks}["taxonomy_governance"]

    assert taxonomy.status == "fail"
    assert "unsupported artifact type invalid-artifact" in taxonomy.detail


def test_artifact_governance_rejects_unsafe_protected_baseline_path(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _write_project(
        project,
        standard="workbench-sdd/v1",
        protected_baseline="""
  protected_baseline:
    - ../outside.mmd
""",
    )
    service = SddPreflightValidationService(
        standard_service=SddStandardService(standards_root=FIXTURE_STANDARDS)
    )

    checks = service.validate_workspace(project)
    governance = {check.name: check for check in checks}["artifact_governance"]

    assert governance.status == "fail"
    assert "Governed path traversal is not allowed: ../outside.mmd" in governance.detail


def test_diagram_metadata_warns_when_sidecars_are_missing(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_project(project, standard="workbench-sdd/v1")
    service = SddPreflightValidationService(
        standard_service=SddStandardService(standards_root=FIXTURE_STANDARDS)
    )

    checks = service.validate_workspace(project)
    diagram_metadata = {check.name: check for check in checks}["diagram_metadata"]

    assert diagram_metadata.status == "warn"
    assert "diagram metadata sidecar(s) missing" in diagram_metadata.detail


def test_diagram_metadata_rejects_missing_required_fields(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_project(project, standard="workbench-sdd/v1")
    (project / "architecture/components.yaml").write_text(
        """diagram_id: components
diagram_type: components
scope: baseline
source: architecture/components.mmd
change_policy: baseline_impact_required
"""
    )
    service = SddPreflightValidationService(
        standard_service=SddStandardService(standards_root=FIXTURE_STANDARDS)
    )

    checks = service.validate_workspace(project)
    diagram_metadata = {check.name: check for check in checks}["diagram_metadata"]

    assert diagram_metadata.status == "fail"
    assert "missing required diagram metadata:" in diagram_metadata.detail
    assert "owner" in diagram_metadata.detail


def test_diagram_metadata_rejects_invalid_owner_and_protected_policy(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _write_project(project, standard="workbench-sdd/v1")
    _write_diagram_metadata(
        project / "architecture/components.yaml",
        diagram_id="components",
        diagram_type="components",
        scope="baseline",
        owner="team",
        source="architecture/components.mmd",
    )
    service = SddPreflightValidationService(
        standard_service=SddStandardService(standards_root=FIXTURE_STANDARDS)
    )

    checks = service.validate_workspace(project)
    diagram_metadata = {check.name: check for check in checks}["diagram_metadata"]

    assert diagram_metadata.status == "fail"
    assert "invalid owner team" in diagram_metadata.detail
    assert "change_policy baseline_impact_required" in diagram_metadata.detail


def test_diagram_metadata_rejects_unsupported_diagram_type(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_project(project, standard="workbench-sdd/v1")
    _write_diagram_metadata(
        project / "specs/001-demo/diagrams/sequence.yaml",
        diagram_id="sequence",
        diagram_type="gantt",
        scope="feature",
        source="specs/001-demo/diagrams/sequence.mmd",
    )
    service = SddPreflightValidationService(
        standard_service=SddStandardService(standards_root=FIXTURE_STANDARDS)
    )

    checks = service.validate_workspace(project)
    diagram_metadata = {check.name: check for check in checks}["diagram_metadata"]

    assert diagram_metadata.status == "fail"
    assert "unsupported diagram_type gantt" in diagram_metadata.detail


def test_diagram_metadata_rejects_malformed_metadata_yaml(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_project(project, standard="workbench-sdd/v1")
    (project / "architecture/components.yaml").write_text("- nope\n")
    service = SddPreflightValidationService(
        standard_service=SddStandardService(standards_root=FIXTURE_STANDARDS)
    )

    checks = service.validate_workspace(project)
    diagram_metadata = {check.name: check for check in checks}["diagram_metadata"]

    assert diagram_metadata.status == "fail"
    assert "metadata must be a mapping" in diagram_metadata.detail


def test_mermaid_validation_rejects_unsupported_source_directive(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _write_project(project, standard="workbench-sdd/v1")
    (project / "architecture/components.mmd").write_text("gantt\n  title Nope\n")
    service = SddPreflightValidationService(
        standard_service=SddStandardService(standards_root=FIXTURE_STANDARDS)
    )

    checks = service.validate_workspace(project)
    mermaid = {check.name: check for check in checks}["mermaid_validation"]

    assert mermaid.status == "fail"
    assert "unsupported Mermaid directive gantt" in mermaid.detail


def test_scaffold_dry_run_blocks_path_traversal(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_project(project, standard="workbench-sdd/v1")
    standards_root = _write_standard_fixture(
        tmp_path / "standards",
        required_artifacts=["../outside.md"],
    )

    result = _run_doctor(project, standards_root=standards_root)

    assert result.returncode == 1
    scaffold = _check(json.loads(result.stdout), "scaffold_dry_run")
    assert scaffold["status"] == "fail"
    assert "path traversal is not allowed: ../outside.md" in scaffold["detail"]


def test_scaffold_dry_run_blocks_absolute_paths(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_project(project, standard="workbench-sdd/v1")
    standards_root = _write_standard_fixture(
        tmp_path / "standards",
        required_artifacts=["/tmp/outside.md"],
    )

    result = _run_doctor(project, standards_root=standards_root)

    assert result.returncode == 1
    scaffold = _check(json.loads(result.stdout), "scaffold_dry_run")
    assert scaffold["status"] == "fail"
    assert "path must be relative: /tmp/outside.md" in scaffold["detail"]


def test_scaffold_dry_run_blocks_specs_root_escape(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_project(project, standard="workbench-sdd/v1")
    standards_root = _write_standard_fixture(
        tmp_path / "standards",
        required_artifacts=["specs/../outside.md"],
    )

    result = _run_doctor(project, standards_root=standards_root)

    assert result.returncode == 1
    scaffold = _check(json.loads(result.stdout), "scaffold_dry_run")
    assert scaffold["status"] == "fail"
    assert "path traversal is not allowed: specs/../outside.md" in scaffold["detail"]


def test_scaffold_dry_run_blocks_duplicate_targets(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _write_project(project, standard="workbench-sdd/v1")
    standards_root = _write_standard_fixture(
        tmp_path / "standards",
        required_artifacts=["domain/glossary.md", "domain/glossary.md"],
    )

    result = _run_doctor(project, standards_root=standards_root)

    assert result.returncode == 1
    scaffold = _check(json.loads(result.stdout), "scaffold_dry_run")
    assert scaffold["status"] == "fail"
    assert "Duplicate scaffold target path: domain/glossary.md" in scaffold["detail"]


def test_scaffold_dry_run_blocks_incompatible_existing_artifacts(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _write_project(project, standard="workbench-sdd/v1")
    (project / ".sdd").write_text("custom file\n")
    service = SddPreflightValidationService(
        standard_service=SddStandardService(standards_root=FIXTURE_STANDARDS)
    )

    checks = service.validate_workspace(project)
    scaffold = {check.name: check for check in checks}["scaffold_dry_run"]

    assert scaffold.status == "fail"
    assert "would overwrite incompatible existing artifact: .sdd" in scaffold.detail


def test_scaffold_dry_run_blocks_when_template_metadata_invalid(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _write_project(project, standard="workbench-sdd/v1")

    result = _run_doctor(project, standards_root=MISSING_TEMPLATE_STANDARDS)

    scaffold = _check(json.loads(result.stdout), "scaffold_dry_run")
    assert scaffold["status"] == "fail"
    assert (
        "template_metadata: Standard is missing templates metadata"
        in scaffold["detail"]
    )


def test_bootstrap_scaffold_creates_missing_artifacts_and_is_idempotent(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _write_project(project, standard="workbench-sdd/v1", with_artifacts=False)
    service = SddPreflightValidationService(
        standard_service=SddStandardService(standards_root=FIXTURE_STANDARDS)
    )

    result = service.bootstrap_scaffold(project)

    assert result.blocked == ()
    assert result.created == (
        ".specify/memory/constitution.md",
        "architecture/overview.md",
        "domain/glossary.md",
        "data/persistence-model.md",
        "specs",
        ".sdd",
    )
    constitution = (project / ".specify/memory/constitution.md").read_text()
    assert "template_id: constitution" in constitution
    assert "# Project Constitution" in constitution
    assert "## Workbench-owned Rules" in constitution
    assert (project / "architecture/overview.md").is_file()
    architecture = (project / "architecture/overview.md").read_text()
    assert "template_id: architecture-overview" in architecture
    assert "## System Context" in architecture
    assert (project / "domain/glossary.md").is_file()
    glossary = (project / "domain/glossary.md").read_text()
    assert "template_id: domain-glossary" in glossary
    assert "## Ubiquitous Language" in glossary
    assert (project / "data/persistence-model.md").is_file()
    persistence = (project / "data/persistence-model.md").read_text()
    assert "template_id: data-persistence-model" in persistence
    assert "## Migration Policy" in persistence
    for generated in (constitution, architecture, glossary, persistence):
        assert "{{" not in generated
        assert "}}" not in generated
        assert "${" not in generated
    assert (project / "specs").is_dir()
    assert (project / ".sdd").is_dir()

    second_result = service.bootstrap_scaffold(project)

    assert second_result.blocked == ()
    assert second_result.created == ()
    assert set(second_result.existing) == set(result.created)
    assert second_result.next_actions == ("No scaffold changes needed.",)


def test_bootstrap_scaffold_blocks_preexisting_file_without_writing(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _write_project(project, standard="workbench-sdd/v1", with_artifacts=False)
    (project / ".sdd").write_text("custom file\n")
    service = SddPreflightValidationService(
        standard_service=SddStandardService(standards_root=FIXTURE_STANDARDS)
    )

    result = service.bootstrap_scaffold(project)

    assert result.created == ()
    assert result.blocked
    assert "would overwrite incompatible existing artifact: .sdd" in result.blocked[0]
    _assert_scaffold_not_written(project, except_paths=(".sdd",))


def test_bootstrap_scaffold_blocks_unsafe_standard_path_without_writing(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _write_project(project, standard="workbench-sdd/v1", with_artifacts=False)
    standards_root = _write_standard_fixture(
        tmp_path / "standards",
        required_artifacts=["../outside.md"],
    )
    service = SddPreflightValidationService(
        standard_service=SddStandardService(standards_root=standards_root)
    )

    result = service.bootstrap_scaffold(project)

    assert result.created == ()
    assert result.blocked
    assert "path traversal is not allowed: ../outside.md" in result.blocked[0]
    assert not (tmp_path / "outside.md").exists()
    _assert_scaffold_not_written(project)


def test_bootstrap_scaffold_blocks_missing_template_metadata_without_writing(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _write_project(project, standard="workbench-sdd/v1", with_artifacts=False)
    service = SddPreflightValidationService(
        standard_service=SddStandardService(standards_root=MISSING_TEMPLATE_STANDARDS)
    )

    result = service.bootstrap_scaffold(project)

    assert result.created == ()
    assert result.blocked
    assert (
        "template_metadata: Standard is missing templates metadata" in result.blocked[0]
    )
    _assert_scaffold_not_written(project)


def test_bootstrap_scaffold_blocks_validator_failure_without_writing(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    _write_project(
        project,
        standard="workbench-sdd/v1",
        context_rules="""
    context_rules:
      unsupported_key:
        - nope
""",
        with_artifacts=False,
    )
    service = SddPreflightValidationService(
        standard_service=SddStandardService(standards_root=FIXTURE_STANDARDS)
    )

    result = service.bootstrap_scaffold(project)

    assert result.created == ()
    assert result.blocked
    assert "context_rules: Unsupported sdd.context_rules key(s)" in result.blocked[0]
    _assert_scaffold_not_written(project)


def _run_doctor(
    project: Path, *, standards_root: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "scripts/codex_bridge_sdd_doctor.py",
            "--workspace",
            str(project),
            "--projects-root",
            str(project.parent),
            "--standards-root",
            str(standards_root),
            "--json",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _check(payload: dict[str, object], name: str) -> dict[str, str]:
    checks = payload["checks"]
    assert isinstance(checks, list)
    for check in checks:
        assert isinstance(check, dict)
        if check.get("name") == name:
            return check
    raise AssertionError(f"Missing check {name}")


def _write_project(
    project: Path,
    *,
    standard: str,
    context_rules: str | None = None,
    protected_baseline: str | None = None,
    with_artifacts: bool = True,
) -> None:
    project.mkdir(parents=True)
    if with_artifacts:
        (project / ".specify/memory").mkdir(parents=True)
        (project / "architecture").mkdir(parents=True)
        (project / "specs/001-demo/diagrams").mkdir(parents=True)
    context_rules_block = (
        context_rules
        or """
context_rules:
  domains:
    workbench:
      modules:
        - backend/app/application/services
      preferred_context:
        - specs/001-demo/spec.md
  excluded_paths:
    - .git
  candidate_limits:
    related_specs: 5
    related_diagrams: 3
"""
    )
    context_rules_block = textwrap.indent(
        textwrap.dedent(context_rules_block).strip(),
        "  ",
    )
    protected_baseline_block = (
        textwrap.indent(textwrap.dedent(protected_baseline).strip(), "  ") + "\n"
        if protected_baseline is not None
        else ""
    )
    (project / "codex-bridge.yaml").write_text(
        f"""kind: codex.bridge.project
version: 1
sdd:
  required: true
  standard: {standard}
  project_type: bridge_backend
  constitution: .specify/memory/constitution.md
  specs: specs
  architecture: architecture
  domain_root: domain
  data_root: data
  generated_index_root: .sdd
{protected_baseline_block}
{context_rules_block}
"""
    )
    if not with_artifacts:
        return
    (project / ".specify/memory/constitution.md").write_text("# Constitution\n")
    (project / "architecture/components.mmd").write_text("flowchart LR\nA --> B\n")
    (project / "specs/001-demo/spec.md").write_text("# Demo Spec\n")
    (project / "specs/001-demo/plan.md").write_text("# Demo Plan\n")
    (project / "specs/001-demo/tasks.md").write_text("# Demo Tasks\n")
    (project / "specs/001-demo/diagrams/sequence.mmd").write_text(
        "sequenceDiagram\nA->>B: hi\n"
    )


def _write_diagram_metadata(
    path: Path,
    *,
    diagram_id: str,
    diagram_type: str,
    scope: str,
    source: str,
    owner: str = "project",
    change_policy: str | None = None,
) -> None:
    change_policy_line = (
        f"change_policy: {change_policy}\n" if change_policy is not None else ""
    )
    path.write_text(
        f"""diagram_id: {diagram_id}
diagram_type: {diagram_type}
scope: {scope}
status: draft
owner: {owner}
source: {source}
{change_policy_line}"""
    )


def _assert_scaffold_not_written(
    project: Path,
    *,
    except_paths: tuple[str, ...] = (),
) -> None:
    expected = (
        ".specify/memory/constitution.md",
        "architecture/overview.md",
        "domain/glossary.md",
        "data/persistence-model.md",
        "specs",
        ".sdd",
    )
    for relative_path in expected:
        if relative_path in except_paths:
            continue
        assert not (project / relative_path).exists(), relative_path


def _write_standard_fixture(
    root: Path,
    *,
    required_artifacts: list[str],
    malformed_template_metadata: bool = False,
    invalid_template_artifact_type: bool = False,
) -> Path:
    standard_dir = root / "workbench-sdd"
    templates_dir = standard_dir / "templates"
    templates_dir.mkdir(parents=True)
    artifact_lines = "\n".join(f"    - {path}" for path in required_artifacts)
    constitution_source_line = (
        ""
        if malformed_template_metadata
        else "      source: templates/constitution.md\n"
    )
    constitution_artifact_type = (
        "invalid-artifact" if invalid_template_artifact_type else "constitution"
    )
    (standard_dir / "v1.yaml").write_text(
        f"""kind: codex.workbenchSddStandard
id: workbench-sdd/v1
version: 1
compatibility:
  supported_ids:
    - workbench-sdd/v1
artifact_types:
  required:
    - manifest
    - constitution
    - architecture
    - domain
    - data
    - spec
    - plan
    - tasks
    - traceability
    - diagram
    - generated_index
  optional:
    - architecture-decision
    - diagram-metadata
ownership:
  allowed_owners:
    - workbench
    - project
  workbench_owned:
    - standard
    - template
    - taxonomy
    - validation_rule
  project_owned:
    - manifest
    - constitution
    - architecture
    - domain
    - data
    - spec
    - plan
    - tasks
    - traceability
    - diagram
    - generated_index
diagram_taxonomy:
  required_metadata:
    - diagram_id
    - diagram_type
    - scope
    - status
    - owner
    - source
  baseline:
    - system-context
    - components
    - deployment
    - domain-model
    - entity-relationship
  feature:
    - sequence
    - state
    - component-impact
    - domain-impact
    - data-impact
  notation:
    system-context: mermaid.flowchart
    components: mermaid.flowchart
    deployment: mermaid.flowchart
    domain-model: mermaid.classDiagram
    entity-relationship: mermaid.erDiagram
    sequence: mermaid.sequenceDiagram
    state: mermaid.stateDiagram-v2
    component-impact: mermaid.flowchart
    domain-impact: mermaid.classDiagram
    data-impact: mermaid.erDiagram
  source_directives:
    mermaid.flowchart:
      - flowchart
      - graph
    mermaid.sequenceDiagram:
      - sequenceDiagram
    mermaid.stateDiagram-v2:
      - stateDiagram
      - stateDiagram-v2
    mermaid.classDiagram:
      - classDiagram
    mermaid.erDiagram:
      - erDiagram
diagram_governance:
  baseline_scope: baseline
  feature_scope: feature
  protected_baseline_policy: baseline_impact_required
  baseline_path_prefixes:
    - architecture/
  feature_path_prefixes:
    - specs/
  missing_metadata_policy: warn
  render_validation_policy: not_available_without_configured_renderer
  syntax_validation_policy: source_directive_and_basic_structure
context_rules:
  required_safety_rules:
    - manifest_first_resolution
    - baseline_impact_gates
    - no_broad_read
    - unknown_version_hard_failure
  allowed_override_keys:
    - domains
    - excluded_paths
    - candidate_limits
    - protected_baseline
    - preferred_context
candidate_limits:
  related_specs: 5
  related_diagrams: 3
templates:
  required_metadata:
    - template_id
    - artifact_type
    - destination
    - source
  required:
    - constitution
    - architecture-overview
    - domain-glossary
    - data-persistence-model
  catalog:
    constitution:
      template_id: constitution
      artifact_type: {constitution_artifact_type}
      destination: .specify/memory/constitution.md
{constitution_source_line}    architecture-overview:
      template_id: architecture-overview
      artifact_type: architecture
      destination: architecture/overview.md
      source: templates/architecture-overview.md
    domain-glossary:
      template_id: domain-glossary
      artifact_type: domain
      destination: domain/glossary.md
      source: templates/domain-glossary.md
    data-persistence-model:
      template_id: data-persistence-model
      artifact_type: data
      destination: data/persistence-model.md
      source: templates/data-persistence-model.md
scaffold:
  required_artifacts:
{artifact_lines}
"""
    )
    for template_id, title in {
        "constitution": "Project Constitution",
        "architecture-overview": "Architecture Overview",
        "domain-glossary": "Domain Glossary",
        "data-persistence-model": "Persistence Model",
    }.items():
        (templates_dir / f"{template_id}.md").write_text(
            f"""---
template_id: {template_id}
artifact_type: test
status: draft
owner: project
---

# {title}
"""
        )
    (standard_dir / "llm-resolution.md").write_text(
        "Requested standard: {requested_id}\n"
        "Canonical standard: {canonical_id}\n"
        "Canonical in-repo artifact: {canonical_artifact}\n"
        "Loaded artifact: {loaded_artifact}\n"
        "Version semantics: {version_semantics}\n"
    )
    return root
