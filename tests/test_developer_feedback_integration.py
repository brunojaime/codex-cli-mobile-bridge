from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts/developer_feedback_integration.py"
SPEC = importlib.util.spec_from_file_location(
    "developer_feedback_integration",
    SCRIPT_PATH,
)
assert SPEC is not None
feedback = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = feedback
SPEC.loader.exec_module(feedback)


def test_doctor_passes_for_complete_registered_app(tmp_path: Path) -> None:
    fixture = _write_fixture(tmp_path)

    payload = _run_script(
        [
            "--associations",
            str(fixture.associations),
            "--registry",
            str(fixture.registry),
            "--workspace-aliases",
            f"fixture-app:{fixture.app_repo}",
            "--json",
        ]
    )

    report = json.loads(payload.stdout)[0]
    assert report["sourceApp"] == "fixture-app"
    assert report["ok"] is True
    assert {item["status"] for item in report["checks"]} == {"pass"}


def test_doctor_fails_when_dependency_is_missing(tmp_path: Path) -> None:
    fixture = _write_fixture(tmp_path, include_dependency=False)
    component = feedback.load_component(fixture.associations, "codex_developer_feedback_template")
    report = feedback.build_report(
        component=component,
        app=component.apps[0],
        registry=feedback.load_registry(fixture.registry),
        workspace_aliases={"fixture-app": str(fixture.app_repo)},
    )

    failed = [check for check in report.checks if check.status == "fail"]
    assert any(check.name == "dependency" for check in failed)
    assert not report.ok


def test_doctor_fails_when_wrapper_is_missing(tmp_path: Path) -> None:
    fixture = _write_fixture(tmp_path, include_wrapper=False)
    component = feedback.load_component(fixture.associations, "codex_developer_feedback_template")
    report = feedback.build_report(
        component=component,
        app=component.apps[0],
        registry=feedback.load_registry(fixture.registry),
        workspace_aliases={"fixture-app": str(fixture.app_repo)},
    )

    failed = [check for check in report.checks if check.status == "fail"]
    assert any(check.name == "wrapper" for check in failed)
    assert not report.ok


def test_doctor_fails_when_template_ref_is_too_old(tmp_path: Path) -> None:
    fixture = _write_fixture(tmp_path, dependency_ref="codex-developer-feedback-template-v0.3.10")
    component = feedback.load_component(fixture.associations, "codex_developer_feedback_template")
    report = feedback.build_report(
        component=component,
        app=component.apps[0],
        registry=feedback.load_registry(fixture.registry),
        workspace_aliases={"fixture-app": str(fixture.app_repo)},
    )

    failed = [check for check in report.checks if check.status == "fail"]
    assert any(check.name == "dependency_ref_latest" for check in failed)
    assert any(check.name == "dependency_ref_minimum" for check in failed)
    assert not report.ok


def test_doctor_fails_when_template_ref_is_not_latest(tmp_path: Path) -> None:
    fixture = _write_fixture(tmp_path, dependency_ref="codex-developer-feedback-template-v0.4.2")
    component = feedback.load_component(fixture.associations, "codex_developer_feedback_template")
    report = feedback.build_report(
        component=component,
        app=component.apps[0],
        registry=feedback.load_registry(fixture.registry),
        workspace_aliases={"fixture-app": str(fixture.app_repo)},
    )

    failed = [check for check in report.checks if check.status == "fail"]
    assert any(check.name == "dependency_ref_latest" for check in failed)
    assert not report.ok


def test_doctor_fails_when_direct_updater_ref_is_not_coordinated(
    tmp_path: Path,
) -> None:
    fixture = _write_fixture(
        tmp_path,
        include_updater_dependency=True,
        updater_dependency_ref="codex-app-updater-v0.1.2",
    )
    component = feedback.load_component(fixture.associations, "codex_developer_feedback_template")
    report = feedback.build_report(
        component=component,
        app=component.apps[0],
        registry=feedback.load_registry(fixture.registry),
        workspace_aliases={"fixture-app": str(fixture.app_repo)},
    )

    failed = [check for check in report.checks if check.status == "fail"]
    assert any(check.name == "codex_app_updater_ref" for check in failed)
    assert not report.ok


def test_doctor_fails_when_role_gate_is_missing(tmp_path: Path) -> None:
    fixture = _write_fixture(tmp_path, include_role_gate=False)
    component = feedback.load_component(fixture.associations, "codex_developer_feedback_template")
    report = feedback.build_report(
        component=component,
        app=component.apps[0],
        registry=feedback.load_registry(fixture.registry),
        workspace_aliases={"fixture-app": str(fixture.app_repo)},
    )

    failed = [check for check in report.checks if check.status == "fail"]
    assert any(check.name == "role_gate" for check in failed)
    assert not report.ok


def test_doctor_fails_when_local_demo_skips_package_contract(tmp_path: Path) -> None:
    fixture = _write_fixture(
        tmp_path,
        include_local_demo_contract=False,
        legacy_local_demo_without_contract=True,
    )
    component = feedback.load_component(fixture.associations, "codex_developer_feedback_template")
    report = feedback.build_report(
        component=component,
        app=component.apps[0],
        registry=feedback.load_registry(fixture.registry),
        workspace_aliases={"fixture-app": str(fixture.app_repo)},
    )

    failed = [check for check in report.checks if check.status == "fail"]
    assert any(check.name == "local_demo_contract" for check in failed)
    assert not report.ok


def test_doctor_fails_when_template_is_conditionally_mounted(tmp_path: Path) -> None:
    fixture = _write_fixture(tmp_path, conditional_wrapper=True)
    component = feedback.load_component(fixture.associations, "codex_developer_feedback_template")
    report = feedback.build_report(
        component=component,
        app=component.apps[0],
        registry=feedback.load_registry(fixture.registry),
        workspace_aliases={"fixture-app": str(fixture.app_repo)},
    )

    failed = [check for check in report.checks if check.status == "fail"]
    assert any(check.name == "template_always_mounted" for check in failed)
    assert not report.ok


def test_doctor_warns_strict_failure_when_wrapper_wraps_material_app(
    tmp_path: Path,
) -> None:
    fixture = _write_fixture(tmp_path, unsafe_wrapper=True)

    relaxed = _run_script(
        [
            "--associations",
            str(fixture.associations),
            "--registry",
            str(fixture.registry),
            "--workspace-aliases",
            f"fixture-app:{fixture.app_repo}",
            "--json",
        ]
    )
    report = json.loads(relaxed.stdout)[0]
    assert report["ok"] is True
    assert any(
        check["name"] == "wrapper_placement" and check["status"] == "warn"
        for check in report["checks"]
    )

    strict = _run_script(
        [
            "--associations",
            str(fixture.associations),
            "--registry",
            str(fixture.registry),
            "--workspace-aliases",
            f"fixture-app:{fixture.app_repo}",
            "--strict",
        ],
        check=False,
    )
    assert strict.returncode == 1
    assert "wrapper_placement" in strict.stdout


def test_registered_local_path_satisfies_workspace_mapping(tmp_path: Path) -> None:
    fixture = _write_fixture(tmp_path, source_app="fixture-mobile")

    result = _run_script(
        [
            "--associations",
            str(fixture.associations),
            "--registry",
            str(fixture.registry),
            "--json",
        ],
        check=True,
    )
    report = json.loads(result.stdout)[0]
    assert report["ok"] is True
    assert any(
        check["name"] == "workspace_alias" and check["status"] == "pass"
        for check in report["checks"]
    )


def test_selecting_unknown_app_fails(tmp_path: Path) -> None:
    fixture = _write_fixture(tmp_path)

    result = _run_script(
        [
            "--associations",
            str(fixture.associations),
            "--registry",
            str(fixture.registry),
            "--app",
            "missing-app",
        ],
        check=False,
    )

    assert result.returncode == 1
    assert "Unknown app" in result.stderr


def test_default_feedback_component_is_configured() -> None:
    component = feedback.load_component(
        feedback.DEFAULT_ASSOCIATIONS,
        "codex_developer_feedback_template",
    )

    assert component.dependency_name == "codex_developer_feedback_template"
    assert component.dependency_ref_prefix == "codex-developer-feedback-template-v"
    assert component.apps


class Fixture:
    def __init__(self, *, associations: Path, registry: Path, app_repo: Path) -> None:
        self.associations = associations
        self.registry = registry
        self.app_repo = app_repo


def _write_fixture(
    tmp_path: Path,
    *,
    source_app: str = "fixture-app",
    display_name: str = "Fixture App",
    include_dependency: bool = True,
    include_wrapper: bool = True,
    include_role_gate: bool = True,
    unsafe_wrapper: bool = False,
    conditional_wrapper: bool = False,
    include_local_demo_contract: bool = True,
    legacy_local_demo_without_contract: bool = False,
    dependency_ref: str = "codex-developer-feedback-template-v0.4.5",
    include_updater_dependency: bool = False,
    updater_dependency_ref: str = "afbefbb7a6b1f8a928af07d2889a266a45eaba82",
) -> Fixture:
    app_repo = tmp_path / "fixture_app"
    app_dir = app_repo / "frontend"
    (app_dir / "lib").mkdir(parents=True)
    (app_dir / "test").mkdir(parents=True)
    _write_pubspec(
        app_dir / "pubspec.yaml",
        include_dependency=include_dependency,
        dependency_ref=dependency_ref,
        include_updater_dependency=include_updater_dependency,
        updater_dependency_ref=updater_dependency_ref,
    )
    _write_main(
        app_dir / "lib/main.dart",
        source_app=source_app,
        display_name=display_name,
        include_wrapper=include_wrapper,
        include_role_gate=include_role_gate,
        unsafe_wrapper=unsafe_wrapper,
        conditional_wrapper=conditional_wrapper,
        include_local_demo_contract=include_local_demo_contract,
        legacy_local_demo_without_contract=legacy_local_demo_without_contract,
    )
    (app_dir / "test/widget_test.dart").write_text(
        f"""
import 'package:codex_developer_feedback_template/developer_feedback_template.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {{
  test('configures feedback wrapper', () {{
    expect(DeveloperFeedbackTemplate, isNotNull);
    expect('{source_app}', '{source_app}');
  }});
}}
""".lstrip()
    )
    associations = tmp_path / "associations.json"
    associations.write_text(
        json.dumps(
            {
                "codex_developer_feedback_template": {
                    "displayName": "Codex Developer Feedback Template",
                    "dependencyName": "codex_developer_feedback_template",
                    "dependencyRefPrefix": "codex-developer-feedback-template-v",
                    "apps": [
                        {
                            "sourceApp": source_app,
                            "displayName": display_name,
                            "repo": "example/fixture-app",
                            "localPath": str(app_repo),
                            "pubspecPath": "frontend/pubspec.yaml",
                            "releaseTagPrefix": "android-v",
                            "releaseWorkflow": "Android Release",
                        }
                    ],
                }
            }
        )
    )
    registry = tmp_path / "app_updates.json"
    registry.write_text(
        json.dumps(
            {
                source_app: {
                    "displayName": display_name,
                    "repo": "example/fixture-app",
                    "releaseTagPattern": "android-v*",
                    "apkAssetPattern": "fixture-app-*.apk",
                    "latestAssetName": "fixture-app.apk",
                    "enabled": True,
                }
            }
        )
    )
    return Fixture(associations=associations, registry=registry, app_repo=app_repo)


def _write_pubspec(
    path: Path,
    *,
    include_dependency: bool,
    dependency_ref: str,
    include_updater_dependency: bool,
    updater_dependency_ref: str,
) -> None:
    dependency = (
        f"""
  codex_developer_feedback_template:
    git:
      url: https://github.com/brunojaime/codex-cli-mobile-bridge.git
      path: packages/codex_developer_feedback_template
      ref: {dependency_ref}
"""
        if include_dependency
        else ""
    )
    updater_dependency = (
        f"""
  codex_app_updater:
    git:
      url: https://github.com/brunojaime/codex-cli-mobile-bridge.git
      path: packages/codex_app_updater
      ref: {updater_dependency_ref}
"""
        if include_updater_dependency
        else ""
    )
    path.write_text(
        f"""
name: fixture_app
version: 1.0.0+1
dependencies:
  flutter:
    sdk: flutter
{dependency}
{updater_dependency}
""".lstrip()
    )


def _write_main(
    path: Path,
    *,
    source_app: str,
    display_name: str,
    include_wrapper: bool,
    include_role_gate: bool,
    unsafe_wrapper: bool,
    conditional_wrapper: bool,
    include_local_demo_contract: bool,
    legacy_local_demo_without_contract: bool,
) -> None:
    safe_wrapper = """
MaterialApp(
  builder: (context, child) {
    return DeveloperFeedbackTemplate(
      enabled: developerFeedbackTemplateEnabled,
      sourceApp: _feedbackSourceApp,
      sourceDisplayName: _feedbackSourceDisplayName,
      bridgeUrl: developerFeedbackBridgeUrl,
      appUpdaterBridgeUrl: developerFeedbackAppUpdaterBridgeUrl,
      child: child ?? const SizedBox.shrink(),
    );
  },
  home: const SizedBox.shrink(),
)
"""
    role_gate_wrapper = """
CodexDeveloperRoleGate(
  child: MaterialApp(
    builder: (context, child) {
      return DeveloperFeedbackTemplate(
        enabled: developerFeedbackTemplateEnabled,
        sourceApp: _feedbackSourceApp,
        sourceDisplayName: _feedbackSourceDisplayName,
        bridgeUrl: developerFeedbackBridgeUrl,
        appUpdaterBridgeUrl: developerFeedbackAppUpdaterBridgeUrl,
        child: child ?? const SizedBox.shrink(),
      );
    },
    home: const SizedBox.shrink(),
  ),
)
"""
    conditional = """
MaterialApp(
  builder: (context, child) {
    Widget wrapped = child ?? const SizedBox.shrink();
    wrapped = CodexDeveloperRoleGate(child: wrapped);
    if (developerFeedbackTemplateEnabled) {
      wrapped = DeveloperFeedbackTemplate(
        enabled: true,
        sourceApp: _feedbackSourceApp,
        sourceDisplayName: _feedbackSourceDisplayName,
        bridgeUrl: developerFeedbackBridgeUrl,
        appUpdaterBridgeUrl: developerFeedbackAppUpdaterBridgeUrl,
        child: wrapped,
      );
    }
    return wrapped;
  },
  home: const SizedBox.shrink(),
)
"""
    unsafe = """
CodexDeveloperRoleGate(
  child: DeveloperFeedbackTemplate(
    enabled: developerFeedbackTemplateEnabled,
    sourceApp: _feedbackSourceApp,
    sourceDisplayName: _feedbackSourceDisplayName,
    bridgeUrl: developerFeedbackBridgeUrl,
    appUpdaterBridgeUrl: developerFeedbackAppUpdaterBridgeUrl,
    child: MaterialApp(home: const SizedBox.shrink()),
  ),
)
"""
    wrapper = (
        unsafe
        if unsafe_wrapper
        else conditional
        if conditional_wrapper
        else safe_wrapper
        if include_wrapper and not include_role_gate
        else role_gate_wrapper
        if include_wrapper
        else "MaterialApp(home: SizedBox.shrink())"
    )
    if include_local_demo_contract:
        local_demo_code = f"""
const localDemoConfig = CodexLocalDemoConfig.fromEnvironment;
const localDemoDescriptor = CodexLocalDemoDescriptor(
  appName: '{display_name}',
  tenant: 'tenant-demo',
  email: 'owner@example.com',
  password: 'StrongPass123',
  highlights: ['Seeded workspace'],
);
"""
    elif legacy_local_demo_without_contract:
        local_demo_code = """
const localDemoMode = bool.fromEnvironment('LOCAL_DEMO_MODE');

class LocalDemoBackendApi {
  const LocalDemoBackendApi();
}
"""
    else:
        local_demo_code = ""
    path.write_text(
        f"""
import 'package:codex_developer_feedback_template/developer_feedback_template.dart';
import 'package:flutter/material.dart';

const _feedbackSourceApp = String.fromEnvironment(
  'CODEX_FEEDBACK_SOURCE_APP',
  defaultValue: '{source_app}',
);
const _feedbackSourceDisplayName = String.fromEnvironment(
  'CODEX_FEEDBACK_SOURCE_NAME',
  defaultValue: '{display_name}',
);
{local_demo_code}

class App extends StatelessWidget {{
  const App({{super.key}});

  @override
  Widget build(BuildContext context) {{
    return {wrapper};
  }}
}}
""".lstrip()
    )


def _run_script(
    args: list[str],
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
