"""The DEV automation revision is captured once, when the backend loads."""
import json
from pathlib import Path
import re


def read_revision(root):
    try:
        value = json.loads((Path(root) / '.run/bridge-autofix/loaded-release.json').read_text())['commit']
        return value if isinstance(value, str) and re.fullmatch(r'[a-f0-9]{40}', value) else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


LOADED_REVISION = read_revision(Path(__file__).resolve().parents[4])


def loaded_revision():
    return LOADED_REVISION
