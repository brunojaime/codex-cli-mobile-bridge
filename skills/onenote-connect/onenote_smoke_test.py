from __future__ import annotations

from typing import Sequence

from _launcher import load_scripts_module


def main(argv: Sequence[str] | None = None) -> int:
    module = load_scripts_module(current_file=__file__, module_name="onenote_smoke_test")
    return module.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
