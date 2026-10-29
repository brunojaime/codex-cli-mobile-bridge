import importlib.util
import json
import hashlib
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "feedback_conformance",
    Path(__file__).resolve().parents[1] / "scripts/feedback_conformance.py",
)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def fixture(tmp_path):
    artifact = tmp_path / "shared.tgz"
    artifact.write_bytes(b"approved immutable package")
    installed = tmp_path / "node_modules/@codex/developer-feedback-web"
    installed.mkdir(parents=True)
    (installed / "index.js").write_text("approved")
    release = tmp_path / "release.json"
    release.write_text(
        json.dumps(
            {
                "id": "test-1",
                "packages": {
                    "web": {
                        "version": "0.8.0",
                        "files": {"index.js": hashlib.sha256(b"approved").hexdigest()},
                        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                    }
                },
            }
        )
    )
    (tmp_path / "package.json").write_text(
        json.dumps(
            {"dependencies": {"@codex/developer-feedback-web": "file:shared.tgz"}}
        )
    )
    (tmp_path / "entry.js").write_text(
        "import {mountFeedback} from '@codex/developer-feedback-web'; mountFeedback(config);"
    )
    (tmp_path / "feedback.project.json").write_text(
        json.dumps(
            {
                "schema": "codex.feedback-consumer/v1",
                "sourceApp": "fixture-app",
                "platform": "web",
                "release": "test-1",
                "artifact": "shared.tgz",
                "packageManifest": "package.json",
                "entryPoints": ["entry.js"],
                "enabledEnvironments": ["dev"],
                "queueScopePolicy": "session",
            }
        )
    )
    return release


def test_consumer_and_tampered_artifact(tmp_path):
    release = fixture(tmp_path)
    assert module.assess(tmp_path, release)["ok"]
    (tmp_path / "shared.tgz").write_bytes(b"local patch")
    assert not module.assess(tmp_path, release)["ok"]


def test_reject_local_transport_private_dom_and_production(tmp_path):
    release = fixture(tmp_path)
    for bad in (
        "fetch('/developer-feedback/batches')",
        "host.shadowRoot.append(style)",
    ):
        (tmp_path / "entry.js").write_text(
            "import {mountFeedback} from '@codex/developer-feedback-web'; mountFeedback(config);"
            + bad
        )
        assert not module.assess(tmp_path, release)["ok"]
    manifest = json.loads((tmp_path / "feedback.project.json").read_text())
    manifest["enabledEnvironments"] = ["dev", "prod"]
    (tmp_path / "feedback.project.json").write_text(json.dumps(manifest))
    assert not module.assess(tmp_path, release)["ok"]
