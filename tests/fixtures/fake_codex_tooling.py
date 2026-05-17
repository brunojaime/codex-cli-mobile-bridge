from __future__ import annotations

import sys


def main() -> int:
    args = sys.argv[1:]
    if args == ["--version"]:
        print("codex 9.9.9-test")
        return 0
    if args == ["login", "status"]:
        print("Logged in using ChatGPT")
        return 0
    if args == ["mcp", "list"]:
        print("github: GitHub connector available")
        print("notion: Notion docs")
        return 0
    print(f"unsupported args: {args}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
