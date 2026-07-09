from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


_SKILL_ROOT = Path(__file__).resolve().parents[1] / "skills" / "onenote-connect"
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))

from _launcher import bootstrap_scripts_path  # noqa: E402


def test_onenote_launcher_passes_arguments_through(monkeypatch) -> None:
    launcher = _load_module(_SKILL_ROOT / "onenote.py", "repo_onenote_launcher")
    calls: list[list[str]] = []

    def fake_cli_main(argv=None):
        calls.append(list(argv or []))
        return 23

    monkeypatch.setattr(
        launcher,
        "load_scripts_module",
        lambda *, current_file, module_name: SimpleNamespace(main=fake_cli_main),
    )

    exit_code = launcher.main(["list-pages", "--json"])

    assert exit_code == 23
    assert calls == [["list-pages", "--json"]]


def test_launcher_bootstrap_works_from_copied_install_directory(
    tmp_path: Path, monkeypatch
) -> None:
    copied_skill = tmp_path / "onenote-connect"
    copied_scripts = copied_skill / "scripts"
    copied_scripts.mkdir(parents=True)
    (copied_skill / "_launcher.py").write_text(
        (_SKILL_ROOT / "_launcher.py").read_text()
    )
    (copied_skill / "onenote.py").write_text((_SKILL_ROOT / "onenote.py").read_text())
    (copied_scripts / "onenote_cli.py").write_text(
        "def main(argv=None):\n    assert argv == ['whoami']\n    return 41\n"
    )

    monkeypatch.syspath_prepend(str(copied_skill))
    monkeypatch.delitem(sys.modules, "onenote_cli", raising=False)
    launcher = _load_module(copied_skill / "onenote.py", "copied_onenote_launcher")

    exit_code = launcher.main(["whoami"])

    assert exit_code == 41
    assert str(copied_scripts.resolve()) in sys.path


def test_bootstrap_scripts_path_fails_clearly_when_scripts_directory_is_missing(
    tmp_path: Path,
) -> None:
    missing_launcher = tmp_path / "copied-skill" / "onenote.py"
    missing_launcher.parent.mkdir(parents=True)
    missing_launcher.write_text("# launcher placeholder\n")

    with pytest.raises(RuntimeError) as excinfo:
        bootstrap_scripts_path(missing_launcher)

    assert "Expected scripts directory next to launcher" in str(excinfo.value)


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
