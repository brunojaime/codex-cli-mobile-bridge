from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import sys


DEFAULT_SKILLS_DIR = Path.home() / ".codex" / "skills"


class SkillInstallError(RuntimeError):
    pass


@dataclass(slots=True, frozen=True)
class SkillInstallResult:
    action: str
    mode: str
    source: Path
    target: Path
    changed: bool


def install_skill(
    *,
    source_dir: Path | None = None,
    skills_dir: Path | None = None,
    mode: str = "symlink",
    overwrite: bool = False,
    dry_run: bool = False,
) -> SkillInstallResult:
    source = (source_dir or Path(__file__).resolve().parent.parent).resolve()
    target_root = (skills_dir or DEFAULT_SKILLS_DIR).expanduser()
    target = target_root / source.name

    if mode not in {"symlink", "copy"}:
        raise SkillInstallError(f"Unsupported install mode: {mode}")

    if mode == "symlink":
        return _install_symlink(
            source=source,
            target_root=target_root,
            target=target,
            overwrite=overwrite,
            dry_run=dry_run,
        )

    return _install_copy(
        source=source,
        target_root=target_root,
        target=target,
        overwrite=overwrite,
        dry_run=dry_run,
    )


def uninstall_skill(
    *,
    source_dir: Path | None = None,
    skills_dir: Path | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> SkillInstallResult:
    source = (source_dir or Path(__file__).resolve().parent.parent).resolve()
    target_root = (skills_dir or DEFAULT_SKILLS_DIR).expanduser()
    target = target_root / source.name

    if not target.exists() and not target.is_symlink():
        raise SkillInstallError(f"Installed skill target does not exist: {target}")

    mode = _detect_installed_mode(target)
    expected_target = _is_expected_install_target(target, source)
    if not expected_target and not force:
        raise SkillInstallError(
            f"Target exists but is not the expected installed OneNote skill: {target}. "
            "Pass --force to remove it."
        )

    if dry_run:
        return SkillInstallResult(
            action="would-remove",
            mode=mode,
            source=source,
            target=target,
            changed=True,
        )

    _remove_existing_target(target)
    return SkillInstallResult(
        action="removed",
        mode=mode,
        source=source,
        target=target,
        changed=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create or update the ~/.codex/skills install for this skill.",
    )
    parser.add_argument(
        "--skills-dir",
        type=Path,
        default=DEFAULT_SKILLS_DIR,
        help="Destination skills directory. Defaults to ~/.codex/skills.",
    )
    parser.add_argument(
        "--mode",
        choices=("symlink", "copy"),
        default="symlink",
        help="Install mode. Use 'symlink' for active repo development or 'copy' for a standalone snapshot.",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove the installed skill instead of installing it.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing install target when it does not match the requested install.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow uninstall to remove an unexpected target at the skill install path.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without touching the filesystem.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit structured JSON output for automation.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.uninstall:
            result = uninstall_skill(
                skills_dir=args.skills_dir,
                dry_run=args.dry_run,
                force=args.force,
            )
        else:
            result = install_skill(
                skills_dir=args.skills_dir,
                mode=args.mode,
                overwrite=args.overwrite,
                dry_run=args.dry_run,
            )
    except SkillInstallError as exc:
        if args.json:
            _write_json(
                {
                    "ok": False,
                    "error": str(exc),
                    "dry_run": args.dry_run,
                },
                stream=sys.stdout,
            )
            return 1
        print(str(exc), file=sys.stderr)
        return 1

    if args.json:
        _write_json(_result_payload(result, dry_run=args.dry_run), stream=sys.stdout)
        return 0

    if result.changed:
        if args.dry_run:
            print(
                f"Dry run: {result.action} ({result.mode}) {result.target} -> {result.source}",
                file=sys.stdout,
            )
        else:
            print(
                f"{result.action} ({result.mode}): {result.target} -> {result.source}",
                file=sys.stdout,
            )
        return 0

    print(f"already installed ({result.mode}): {result.target}", file=sys.stdout)
    return 0


def _result_payload(result: SkillInstallResult, *, dry_run: bool) -> dict[str, object]:
    return {
        "ok": True,
        "action": result.action,
        "mode": result.mode,
        "source": str(result.source),
        "target": str(result.target),
        "changed": result.changed,
        "dry_run": dry_run,
    }


def _write_json(payload: dict[str, object], *, stream: object) -> None:
    json.dump(payload, stream, indent=2)
    stream.write("\n")


def _install_symlink(
    *,
    source: Path,
    target_root: Path,
    target: Path,
    overwrite: bool,
    dry_run: bool,
) -> SkillInstallResult:
    if target.is_symlink():
        if _symlink_points_to_source(target, source):
            return SkillInstallResult(
                action="already-linked",
                mode="symlink",
                source=source,
                target=target,
                changed=False,
            )
        if not overwrite:
            raise SkillInstallError(
                f"Target exists and points somewhere else: {target}. "
                "Pass --overwrite to replace it."
            )
        if dry_run:
            return SkillInstallResult(
                action="would-replace-link",
                mode="symlink",
                source=source,
                target=target,
                changed=True,
            )
        target.unlink()
    elif target.exists():
        if not overwrite:
            raise SkillInstallError(
                f"Target exists and is not the expected symlink: {target}. "
                "Pass --overwrite to replace it."
            )
        if dry_run:
            return SkillInstallResult(
                action="would-replace-existing",
                mode="symlink",
                source=source,
                target=target,
                changed=True,
            )
        _remove_existing_target(target)
    else:
        if dry_run:
            return SkillInstallResult(
                action="would-link",
                mode="symlink",
                source=source,
                target=target,
                changed=True,
            )

    if not dry_run:
        target_root.mkdir(parents=True, exist_ok=True)
        target.symlink_to(source)

    return SkillInstallResult(
        action="linked" if not overwrite else "relinked",
        mode="symlink",
        source=source,
        target=target,
        changed=True,
    )


def _install_copy(
    *,
    source: Path,
    target_root: Path,
    target: Path,
    overwrite: bool,
    dry_run: bool,
) -> SkillInstallResult:
    if target.exists() or target.is_symlink():
        if target.is_dir() and not target.is_symlink() and _copy_matches_source(target, source):
            return SkillInstallResult(
                action="already-copied",
                mode="copy",
                source=source,
                target=target,
                changed=False,
            )
        if not overwrite:
            raise SkillInstallError(
                f"Target exists and is not the expected copied skill: {target}. "
                "Pass --overwrite to replace it."
            )
        if dry_run:
            return SkillInstallResult(
                action="would-replace-existing",
                mode="copy",
                source=source,
                target=target,
                changed=True,
            )
        _remove_existing_target(target)
    elif dry_run:
        return SkillInstallResult(
            action="would-copy",
            mode="copy",
            source=source,
            target=target,
            changed=True,
        )

    if not dry_run:
        target_root.mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            source,
            target,
            ignore=_copy_ignore,
            symlinks=False,
        )

    return SkillInstallResult(
        action="copied" if not overwrite else "recopied",
        mode="copy",
        source=source,
        target=target,
        changed=True,
    )


def _symlink_points_to_source(target: Path, source: Path) -> bool:
    try:
        return target.resolve() == source
    except OSError:
        return False


def _remove_existing_target(target: Path) -> None:
    if target.is_symlink():
        target.unlink()
        return
    if target.is_dir():
        shutil.rmtree(target)
        return
    target.unlink()


def _detect_installed_mode(target: Path) -> str:
    if target.is_symlink():
        return "symlink"
    if target.is_dir():
        return "copy"
    return "file"


def _is_expected_install_target(target: Path, source: Path) -> bool:
    if target.is_symlink():
        return _symlink_points_to_source(target, source)
    if target.is_dir():
        return _copy_matches_source(target, source)
    return False


def _copy_matches_source(target: Path, source: Path) -> bool:
    for relative_path in _iter_copyable_relative_paths(source):
        if not (target / relative_path).exists():
            return False
    return True


def _iter_copyable_relative_paths(source: Path) -> list[Path]:
    paths: list[Path] = []
    for path in source.rglob("*"):
        relative_path = path.relative_to(source)
        if _should_skip_copy_path(relative_path):
            continue
        paths.append(relative_path)
    return paths


def _copy_ignore(_directory: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for name in names:
        if _should_skip_copy_path(Path(name)):
            ignored.add(name)
    return ignored


def _should_skip_copy_path(relative_path: Path) -> bool:
    ignored_names = {
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".DS_Store",
    }
    if any(part in ignored_names for part in relative_path.parts):
        return True
    return relative_path.suffix in {".pyc", ".pyo"}


if __name__ == "__main__":
    raise SystemExit(main())
