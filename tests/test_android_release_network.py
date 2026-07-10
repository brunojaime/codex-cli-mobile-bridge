from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/validate_android_release_network.py"


def _load_validator():
    spec = importlib.util.spec_from_file_location(
        "validate_android_release_network",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_android_release_network_allows_real_tailnet_http_host():
    validator = _load_validator()

    errors = validator.validate(
        REPO_ROOT,
        api_base_url="http://batata-default-string.tail0302c4.ts.net",
        updater_bridge_url="http://batata-default-string.tail0302c4.ts.net",
    )

    assert errors == []


def test_android_release_network_rejects_unconfigured_http_host():
    validator = _load_validator()

    errors = validator.validate(
        REPO_ROOT,
        api_base_url="http://other-tailnet-host.tail0302c4.ts.net",
        updater_bridge_url="http://other-tailnet-host.tail0302c4.ts.net",
    )

    assert errors == [
        "networkSecurityConfig does not permit cleartext HTTP for "
        "other-tailnet-host.tail0302c4.ts.net."
    ]


def test_android_release_network_rejects_local_or_placeholder_urls():
    validator = _load_validator()

    local_errors = validator.validate(
        REPO_ROOT,
        api_base_url="http://localhost:8000",
        updater_bridge_url="http://localhost:8000",
    )
    placeholder_errors = validator.validate(
        REPO_ROOT,
        api_base_url="https://placeholder.example.com",
        updater_bridge_url="https://placeholder.example.com",
    )

    assert "API_BASE_URL must not point at a local-only host: localhost" in local_errors
    assert (
        "CODEX_APP_UPDATER_BRIDGE_URL must not point at a local-only host: localhost"
        in local_errors
    )
    assert (
        "API_BASE_URL host looks like a placeholder: placeholder.example.com"
        in placeholder_errors
    )
    assert (
        "CODEX_APP_UPDATER_BRIDGE_URL host looks like a placeholder: "
        "placeholder.example.com"
        in placeholder_errors
    )
