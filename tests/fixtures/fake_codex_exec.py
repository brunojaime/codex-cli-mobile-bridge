from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0] != "exec":
        print("expected exec subcommand", file=sys.stderr)
        return 1

    output_path: Path | None = None
    filtered_args: list[str] = []
    index = 1

    while index < len(args):
        current = args[index]
        if current == "-o":
            output_path = Path(args[index + 1])
            index += 2
            continue

        if current in {"--skip-git-repo-check", "--color"}:
            index += 2 if current == "--color" else 1
            continue

        filtered_args.append(current)
        index += 1

    if not filtered_args:
        print("missing prompt", file=sys.stderr)
        return 1

    prompt = filtered_args[-1]
    if prompt.startswith("fail:"):
        print(prompt.split(":", maxsplit=1)[1], file=sys.stderr)
        return 1

    if output_path is not None:
        output_path.write_text(f"Codex exec response: {prompt}", encoding="utf-8")

    print(f"raw stdout for {prompt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
