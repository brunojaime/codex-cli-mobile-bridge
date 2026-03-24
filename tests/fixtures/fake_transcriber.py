from __future__ import annotations

from pathlib import Path
import sys
import time


def main() -> None:
    args = sys.argv[1:]
    if len(args) >= 2 and args[0] == "--sleep":
        time.sleep(float(args[1]))
        args = args[2:]

    if len(args) >= 2:
        print(f"Transcribed audio from {args[0]}")
        return

    audio_path = Path(args[0]).resolve()
    print(f"Transcribed audio from {audio_path.name}")


if __name__ == "__main__":
    main()
