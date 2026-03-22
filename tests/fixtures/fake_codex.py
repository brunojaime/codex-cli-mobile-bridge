from __future__ import annotations

import sys
import time


def main() -> int:
    if len(sys.argv) < 2:
        print("Missing message.", file=sys.stderr)
        return 1

    message = sys.argv[1]

    if message.startswith("sleep:"):
        _, raw_seconds = message.split(":", maxsplit=1)
        time.sleep(float(raw_seconds))
        print(f"Completed after {raw_seconds}s")
        return 0

    if message.startswith("fail:"):
        _, failure_message = message.split(":", maxsplit=1)
        print(failure_message or "Forced failure", file=sys.stderr)
        return 1

    print(f"Codex response: {message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
