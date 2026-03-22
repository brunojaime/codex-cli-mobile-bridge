from __future__ import annotations

from pathlib import Path
import sys


def main() -> None:
    if len(sys.argv) >= 3:
        print(f"Transcribed audio from {sys.argv[1]}")
        return

    audio_path = Path(sys.argv[1]).resolve()
    print(f"Transcribed audio from {audio_path.name}")


if __name__ == "__main__":
    main()
