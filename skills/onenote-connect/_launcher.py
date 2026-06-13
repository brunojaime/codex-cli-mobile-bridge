from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType


def bootstrap_scripts_path(current_file: str | Path | None = None) -> Path:
    launcher_path = Path(current_file or __file__).resolve()
    scripts_dir = launcher_path.parent / "scripts"
    if not scripts_dir.is_dir():
        raise RuntimeError(f"Expected scripts directory next to launcher: {scripts_dir}")
    scripts_dir_str = str(scripts_dir)
    if scripts_dir_str not in sys.path:
        sys.path.insert(0, scripts_dir_str)
    return scripts_dir


def load_scripts_module(
    *,
    current_file: str | Path,
    module_name: str,
) -> ModuleType:
    scripts_dir = bootstrap_scripts_path(current_file)
    module_path = scripts_dir / f"{module_name}.py"
    if not module_path.is_file():
        raise RuntimeError(f"Expected module at {module_path}")
    spec = importlib.util.spec_from_file_location(
        f"_onenote_connect_{module_name}",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
