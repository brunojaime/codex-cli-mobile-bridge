from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest


_SKILL_SCRIPTS = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "onenote-connect"
    / "scripts"
)
if str(_SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SKILL_SCRIPTS))

from install_skill import SkillInstallError, install_skill, main as install_main, uninstall_skill  # noqa: E402
from install_skill import _should_skip_copy_path  # noqa: E402


def test_install_skill_dry_run_does_not_create_symlink(tmp_path: Path) -> None:
    source = tmp_path / "source-skill"
    source.mkdir()
    skills_dir = tmp_path / "skills-root"

    result = install_skill(
        source_dir=source,
        skills_dir=skills_dir,
        dry_run=True,
    )

    assert result.action == "would-link"
    assert result.mode == "symlink"
    assert result.changed is True
    assert not (skills_dir / source.name).exists()


def test_install_skill_creates_symlink(tmp_path: Path) -> None:
    source = tmp_path / "source-skill"
    source.mkdir()
    skills_dir = tmp_path / "skills-root"

    result = install_skill(
        source_dir=source,
        skills_dir=skills_dir,
    )

    target = skills_dir / source.name
    assert result.action == "linked"
    assert result.mode == "symlink"
    assert target.is_symlink()
    assert target.resolve() == source.resolve()


def test_install_skill_returns_already_linked_for_expected_symlink(tmp_path: Path) -> None:
    source = tmp_path / "source-skill"
    source.mkdir()
    skills_dir = tmp_path / "skills-root"
    skills_dir.mkdir()
    target = skills_dir / source.name
    target.symlink_to(source)

    result = install_skill(
        source_dir=source,
        skills_dir=skills_dir,
    )

    assert result.action == "already-linked"
    assert result.mode == "symlink"
    assert result.changed is False


def test_install_skill_fails_on_conflicting_existing_target_without_overwrite(tmp_path: Path) -> None:
    source = tmp_path / "source-skill"
    source.mkdir()
    skills_dir = tmp_path / "skills-root"
    skills_dir.mkdir()
    target = skills_dir / source.name
    target.write_text("not a symlink")

    with pytest.raises(SkillInstallError) as excinfo:
        install_skill(source_dir=source, skills_dir=skills_dir)

    assert "Target exists and is not the expected symlink" in str(excinfo.value)


def test_install_skill_overwrites_conflicting_symlink_when_requested(tmp_path: Path) -> None:
    source = tmp_path / "source-skill"
    source.mkdir()
    other_source = tmp_path / "other-skill"
    other_source.mkdir()
    skills_dir = tmp_path / "skills-root"
    skills_dir.mkdir()
    target = skills_dir / source.name
    target.symlink_to(other_source)

    result = install_skill(
        source_dir=source,
        skills_dir=skills_dir,
        overwrite=True,
    )

    assert result.action == "relinked"
    assert result.mode == "symlink"
    assert target.is_symlink()
    assert target.resolve() == source.resolve()


def test_install_skill_copy_mode_creates_directory_snapshot(tmp_path: Path) -> None:
    source = _create_source_skill(tmp_path)
    skills_dir = tmp_path / "skills-root"

    result = install_skill(
        source_dir=source,
        skills_dir=skills_dir,
        mode="copy",
    )

    target = skills_dir / source.name
    assert result.action == "copied"
    assert result.mode == "copy"
    assert target.is_dir()
    assert not target.is_symlink()
    assert (target / "SKILL.md").read_text() == "# skill\n"
    assert (target / "scripts" / "run.py").read_text() == "print('ok')\n"
    assert not (target / "__pycache__").exists()
    assert not (target / "scripts" / "__pycache__").exists()
    assert not (target / "scripts" / "run.pyc").exists()


def test_install_skill_copy_mode_overwrites_existing_directory_when_requested(tmp_path: Path) -> None:
    source = _create_source_skill(tmp_path)
    skills_dir = tmp_path / "skills-root"
    target = skills_dir / source.name
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text("old\n")

    result = install_skill(
        source_dir=source,
        skills_dir=skills_dir,
        mode="copy",
        overwrite=True,
    )

    assert result.action == "recopied"
    assert result.mode == "copy"
    assert (target / "SKILL.md").read_text() == "# skill\n"
    assert (target / "scripts" / "run.py").read_text() == "print('ok')\n"


def test_install_skill_copy_mode_dry_run_does_not_create_directory(tmp_path: Path) -> None:
    source = _create_source_skill(tmp_path)
    skills_dir = tmp_path / "skills-root"

    result = install_skill(
        source_dir=source,
        skills_dir=skills_dir,
        mode="copy",
        dry_run=True,
    )

    assert result.action == "would-copy"
    assert result.mode == "copy"
    assert result.changed is True
    assert not (skills_dir / source.name).exists()


def test_copy_mode_returns_already_copied_when_target_matches_snapshot(tmp_path: Path) -> None:
    source = _create_source_skill(tmp_path)
    skills_dir = tmp_path / "skills-root"

    first_result = install_skill(
        source_dir=source,
        skills_dir=skills_dir,
        mode="copy",
    )
    second_result = install_skill(
        source_dir=source,
        skills_dir=skills_dir,
        mode="copy",
    )

    assert first_result.action == "copied"
    assert second_result.action == "already-copied"
    assert second_result.mode == "copy"
    assert second_result.changed is False


def test_should_skip_copy_path_filters_expected_cache_paths() -> None:
    assert _should_skip_copy_path(Path("__pycache__"))
    assert _should_skip_copy_path(Path("scripts/__pycache__/run.cpython-313.pyc"))
    assert _should_skip_copy_path(Path(".pytest_cache/v/cache/nodeids"))
    assert _should_skip_copy_path(Path("scripts/run.pyc"))
    assert not _should_skip_copy_path(Path("scripts/run.py"))
    assert not _should_skip_copy_path(Path("references/graph-endpoints.md"))


def test_uninstall_skill_removes_symlink_install(tmp_path: Path) -> None:
    source = _create_source_skill(tmp_path)
    skills_dir = tmp_path / "skills-root"
    install_skill(source_dir=source, skills_dir=skills_dir)

    result = uninstall_skill(source_dir=source, skills_dir=skills_dir)

    assert result.action == "removed"
    assert result.mode == "symlink"
    assert not (skills_dir / source.name).exists()


def test_uninstall_skill_removes_copy_install(tmp_path: Path) -> None:
    source = _create_source_skill(tmp_path)
    skills_dir = tmp_path / "skills-root"
    install_skill(source_dir=source, skills_dir=skills_dir, mode="copy")

    result = uninstall_skill(source_dir=source, skills_dir=skills_dir)

    assert result.action == "removed"
    assert result.mode == "copy"
    assert not (skills_dir / source.name).exists()


def test_uninstall_skill_dry_run_leaves_install_in_place(tmp_path: Path) -> None:
    source = _create_source_skill(tmp_path)
    skills_dir = tmp_path / "skills-root"
    install_skill(source_dir=source, skills_dir=skills_dir, mode="copy")

    result = uninstall_skill(
        source_dir=source,
        skills_dir=skills_dir,
        dry_run=True,
    )

    assert result.action == "would-remove"
    assert result.mode == "copy"
    assert (skills_dir / source.name).exists()


def test_uninstall_skill_fails_when_target_is_missing(tmp_path: Path) -> None:
    source = _create_source_skill(tmp_path)

    with pytest.raises(SkillInstallError) as excinfo:
        uninstall_skill(source_dir=source, skills_dir=tmp_path / "skills-root")

    assert "Installed skill target does not exist" in str(excinfo.value)


def test_uninstall_skill_fails_for_unexpected_target_without_force(tmp_path: Path) -> None:
    source = _create_source_skill(tmp_path)
    other_source = tmp_path / "other-skill"
    other_source.mkdir()
    skills_dir = tmp_path / "skills-root"
    skills_dir.mkdir()
    target = skills_dir / source.name
    target.symlink_to(other_source)

    with pytest.raises(SkillInstallError) as excinfo:
        uninstall_skill(source_dir=source, skills_dir=skills_dir)

    assert "not the expected installed OneNote skill" in str(excinfo.value)
    assert target.exists()


def test_uninstall_skill_force_removes_unexpected_target(tmp_path: Path) -> None:
    source = _create_source_skill(tmp_path)
    skills_dir = tmp_path / "skills-root"
    target = skills_dir / source.name
    target.mkdir(parents=True)
    (target / "notes.txt").write_text("unexpected")

    result = uninstall_skill(
        source_dir=source,
        skills_dir=skills_dir,
        force=True,
    )

    assert result.action == "removed"
    assert result.mode == "copy"
    assert not target.exists()


def test_install_main_json_output_for_normal_install(tmp_path: Path, monkeypatch, capsys) -> None:
    skills_dir = tmp_path / "skills-root"

    exit_code = install_main(
        [
            "--skills-dir",
            str(skills_dir),
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["action"] == "linked"
    assert payload["mode"] == "symlink"
    assert payload["changed"] is True
    assert payload["dry_run"] is False
    assert payload["target"] == str(skills_dir / "onenote-connect")
    assert captured.err == ""


def test_install_main_json_output_for_dry_run(tmp_path: Path, capsys) -> None:
    skills_dir = tmp_path / "skills-root"

    exit_code = install_main(
        [
            "--skills-dir",
            str(skills_dir),
            "--dry-run",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["action"] == "would-link"
    assert payload["mode"] == "symlink"
    assert payload["changed"] is True
    assert payload["dry_run"] is True
    assert captured.err == ""


def _create_source_skill(tmp_path: Path) -> Path:
    source = tmp_path / "source-skill"
    (source / "scripts").mkdir(parents=True)
    (source / "__pycache__").mkdir()
    (source / "scripts" / "__pycache__").mkdir()
    (source / ".pytest_cache").mkdir()
    (source / "SKILL.md").write_text("# skill\n")
    (source / "scripts" / "run.py").write_text("print('ok')\n")
    (source / "scripts" / "run.pyc").write_text("compiled")
    (source / "__pycache__" / "x.pyc").write_text("cache")
    (source / "scripts" / "__pycache__" / "run.cpython-313.pyc").write_text("cache")
    (source / ".pytest_cache" / "README").write_text("cache")
    return source
