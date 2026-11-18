#!/usr/bin/env python3
"""Local client for the persistent ChatGPT collaboration backend."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.chatgpt_collaboration.client import main

if __name__ == '__main__':
    main()
