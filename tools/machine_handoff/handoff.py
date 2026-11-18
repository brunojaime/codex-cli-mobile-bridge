#!/usr/bin/env python3
"""Explicit Git handoff between development computers; Python stdlib only."""
import argparse
import os
from pathlib import Path
import subprocess
import sys


class HandoffError(Exception):
    pass


def git(repo, *args):
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True,
    )
    if result.returncode:
        # Remote errors can contain credential-bearing URLs. Do not echo them.
        raise HandoffError("Git no pudo completar la operación: " + args[0])
    return result.stdout.strip()


def inspect(repo):
    branch = git(repo, "symbolic-ref", "--quiet", "--short", "HEAD")
    if git(repo, "rev-parse", "--show-prefix"):
        raise HandoffError("Usá la raíz del repositorio como --repo.")
    if git(repo, "status", "--porcelain", "--untracked-files=normal"):
        raise HandoffError(
            "Hay archivos pendientes. Revisalos y hacé un commit de tu trabajo; "
            "no se guardan, descartan ni suben archivos automáticamente."
        )
    for marker in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply"):
        path = Path(git(repo, "rev-parse", "--git-path", marker))
        if not path.is_absolute():
            path = repo / path
        if path.exists():
            raise HandoffError("Hay una operación Git pendiente: " + marker)
    remote = git(repo, "config", "--get", f"branch.{branch}.remote")
    target = git(repo, "config", "--get", f"branch.{branch}.merge")
    if remote == "." or remote.startswith("-") or not target.startswith("refs/heads/"):
        raise HandoffError("Se necesita una rama con upstream remoto configurado.")
    return branch, remote, target


def sync(repo, action):
    branch, remote, target = inspect(repo)
    git(repo, "fetch", remote)
    upstream = git(repo, "rev-parse", "--symbolic-full-name", "@{upstream}")
    ahead, behind = map(int, git(
        repo, "rev-list", "--left-right", "--count", "HEAD..." + upstream,
    ).split())
    print(f"Rama {branch}: {ahead} commits por subir, {behind} por descargar.")
    if action == "status":
        return
    if ahead and behind:
        raise HandoffError("Las copias divergieron. Resolvé los commits antes de cambiar de equipo.")
    if action == "start":
        if ahead:
            raise HandoffError("Esta copia tiene commits sin subir. Completá finish primero.")
        git(repo, "merge", "--ff-only", upstream)
        print("Código actualizado. Podés arrancar el servidor de desarrollo.")
    else:
        if behind:
            raise HandoffError("El remoto tiene cambios nuevos. Revisalos antes de subir.")
        git(repo, "push", remote, "HEAD:" + target)
        git(repo, "fetch", remote)
        if git(repo, "rev-parse", "HEAD") != git(repo, "rev-parse", upstream):
            raise HandoffError("El remoto cambió durante el traspaso. Volvé a revisar status.")
        print("Commits sincronizados. En el otro equipo ejecutá start.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "start", "finish"))
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--run", nargs=argparse.REMAINDER,
                        help="Comando de desarrollo, sólo con start; debe ir al final.")
    args = parser.parse_args()
    if args.run and args.action != "start":
        parser.error("--run sólo está disponible con start")
    repo = args.repo.expanduser().resolve()
    try:
        sync(repo, args.action)
        if args.run:
            os.chdir(repo)
            return subprocess.call(args.run)
    except (HandoffError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
