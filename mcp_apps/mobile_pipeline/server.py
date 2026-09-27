"""Central local release orchestration. No credentials or raw build logs in MCP results."""

from __future__ import annotations
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

mcp = FastMCP(
    "Nienfos Mobile Pipeline",
    json_response=True,
    log_level="WARNING",
    instructions="Build and publish native apps locally. Obtain human publication authorization before publish. A completed build is not a store release. Never return secrets or signing credentials.",
)
ROOT = Path(os.environ.get("PROJECTS_ROOT", str(Path.home() / "Projects"))).resolve()
ENGINE = Path(__file__).with_name("release.mjs")
STATE = Path.home() / ".local/state/nienfos-mobile-jobs"
READ = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
)
WRITE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True
)


def _node() -> str:
    configured = os.environ.get("NIENFOS_MOBILE_NODE")
    if configured:
        return configured
    candidates = sorted(
        (Path.home() / ".nvm/versions/node").glob("v22.*/bin/node"),
        key=lambda p: tuple(int(x) for x in p.parents[1].name[1:].split(".")),
        reverse=True,
    )
    return str(candidates[0]) if candidates else "node"


def _project(name: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,100}", name):
        raise ValueError("Invalid project name")
    root = (ROOT / name).resolve()
    if root.parent != ROOT or not (root / "infra/mobile/project.json").is_file():
        raise ValueError("Project is not enrolled in the mobile pipeline")
    return root


@mcp.tool(annotations=READ)
def list_mobile_projects() -> dict:
    """List enrolled apps and their pinned toolkit version, without secrets."""
    items = []
    for path in sorted(ROOT.iterdir()):
        if path.is_symlink() or not path.is_dir():
            continue
        try:
            p = json.loads((path / "infra/mobile/project.json").read_text())
            r = json.loads((path / "infra/mobile/release.json").read_text())
            if p.get("kind") != "nienfos.mobile-project":
                continue
            items.append(
                {
                    "project": path.name,
                    "sourceApp": p["sourceApp"],
                    "profile": r["profile"],
                    "version": r["version"],
                    "build": r["androidBuild"],
                    "toolkitVersion": r["toolkitVersion"],
                    "toolkitUpdateAvailable": r["toolkitVersion"] != "0.1.0",
                }
            )
        except (OSError, ValueError, KeyError):
            continue
    return {
        "toolkitVersion": "0.1.0",
        "projects": items,
        "updates": "Promote a tested toolkit version per app; native changes require rebuild and publication.",
    }


@mcp.tool(annotations=READ)
def mobile_status(project: str) -> dict:
    """Read configuration and build readiness, without running a build."""
    node = _node()
    result = subprocess.run(
        [node, str(ENGINE), str(_project(project)), "status"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode:
        return {
            "ok": False,
            "reason": "Configuration invalid or toolkit version not promoted",
        }
    return json.loads(result.stdout)


@mcp.tool(annotations=WRITE)
def start_mobile_job(
    project: str, operation: str, approval_reference: str = ""
) -> dict:
    """Start build or GitHub publish. Publish requires authorization and matching runtime evidence; never invokes Actions."""
    root = _project(project)
    if operation not in {"build", "publish"}:
        raise ValueError("Operation must be build or publish")
    if operation == "publish" and not re.fullmatch(
        r"[A-Za-z0-9:/._-]{8,128}", approval_reference
    ):
        raise ValueError("Supply the human authorization reference, never a credential")
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    job_id = str(uuid.uuid4())
    path = STATE / job_id
    path.mkdir(mode=0o700)
    (path / "request.json").write_text(
        json.dumps(
            {
                "project": str(root),
                "operation": operation,
                "approval": approval_reference,
            }
        )
    )
    log = (path / "private.log").open("w")
    os.chmod(path / "private.log", 0o600)
    subprocess.Popen(
        [sys.executable, "-m", "mcp_apps.mobile_pipeline.worker", job_id],
        stdout=log,
        stderr=log,
        start_new_session=True,
        cwd=ENGINE.parents[2],
    )
    log.close()
    return {
        "jobId": job_id,
        "state": "queued",
        "operation": operation,
        "project": project,
    }


@mcp.tool(annotations=READ)
def mobile_job_status(job_id: str) -> dict:
    """Read sanitized job outcome; raw logs and credentials remain private."""
    if not re.fullmatch(r"[a-f0-9-]{36}", job_id):
        raise ValueError("Invalid job id")
    path = STATE / job_id
    if not path.is_dir():
        raise ValueError("Job not found")
    result = path / "result.json"
    return (
        json.loads(result.read_text())
        if result.exists()
        else {"jobId": job_id, "state": "running"}
    )


@mcp.tool(annotations=WRITE)
def prepare_android_signing(project: str) -> dict:
    """Create or reuse a private local Android signing identity; return only its public fingerprint."""
    import hashlib
    import secrets

    root = _project(project)
    manifest = json.loads((root / "infra/mobile/project.json").read_text())
    release_path = root / "infra/mobile/release.json"
    if release_path.is_symlink() or not release_path.resolve().is_relative_to(root):
        raise ValueError("Configuration escapes project")
    release = json.loads(release_path.read_text())
    source = manifest.get("sourceApp", "")
    profile = release.get("profile", "")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,63}", source) or profile not in {
        "preview",
        "staging",
        "production",
    }:
        raise ValueError("Invalid signing identity")
    private = Path.home() / ".local/state/nienfos-mobile-signing"
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    if private.is_symlink() or private.stat().st_mode & 0o077:
        raise ValueError("Signing directory must be private")
    credential = private / f"{source}-{profile}.json"
    key = private / f"{source}-{profile}.jks"
    java = Path(
        os.environ.get("JAVA_HOME", str(Path.home() / ".local/share/java/jdk-17"))
    )
    keytool = java / "bin/keytool"
    if not keytool.is_file():
        raise ValueError("Configure JAVA_HOME with keytool")
    created = False
    if credential.exists():
        if credential.is_symlink() or credential.stat().st_mode & 0o077:
            raise ValueError("Signing credentials must be a private regular file")
        values = json.loads(credential.read_text())
    else:
        if key.exists():
            raise ValueError("Unregistered key exists; recover it without overwriting")
        password = secrets.token_urlsafe(36)
        values = {
            "ANDROID_KEYSTORE_PATH": str(key),
            "ANDROID_STORE_PASSWORD": password,
            "ANDROID_KEY_PASSWORD": password,
            "ANDROID_KEY_ALIAS": "nienfos",
        }
        env = dict(os.environ, NG_SIGN_PASS=password)
        result = subprocess.run(
            [
                str(keytool),
                "-genkeypair",
                "-keystore",
                str(key),
                "-storepass:env",
                "NG_SIGN_PASS",
                "-keypass:env",
                "NG_SIGN_PASS",
                "-alias",
                "nienfos",
                "-keyalg",
                "RSA",
                "-keysize",
                "3072",
                "-validity",
                "10000",
                "-dname",
                "CN=Nienfos Mobile,O=Nienfos,C=AR",
            ],
            env=env,
            capture_output=True,
            timeout=120,
        )
        if result.returncode:
            raise ValueError(
                "Signing key generation failed; inspect private operator state"
            )
        key.chmod(0o600)
        with credential.open("x") as output:
            os.chmod(credential, 0o600)
            output.write(json.dumps(values))
        created = True
    env = dict(os.environ, NG_SIGN_PASS=values["ANDROID_STORE_PASSWORD"])
    result = subprocess.run(
        [
            str(keytool),
            "-exportcert",
            "-keystore",
            values["ANDROID_KEYSTORE_PATH"],
            "-storepass:env",
            "NG_SIGN_PASS",
            "-alias",
            values["ANDROID_KEY_ALIAS"],
        ],
        env=env,
        capture_output=True,
        timeout=60,
    )
    if result.returncode:
        raise ValueError("Existing signing identity could not be verified")
    digest = hashlib.sha256(result.stdout).hexdigest()
    if (
        release.get("signingCertificateSha256")
        and release["signingCertificateSha256"] != digest
    ):
        raise ValueError("Refusing to replace the registered signing identity")
    release["signingCertificateSha256"] = digest
    release_path.write_text(json.dumps(release, indent=2) + "\n")
    return {
        "project": project,
        "profile": profile,
        "created": created,
        "certificateSha256": digest,
        "privateCredentialStored": True,
        "nextStep": "Keep a private recoverable backup; validate and commit the public configuration before build.",
    }


@mcp.tool(annotations=WRITE)
def bump_mobile_version(project: str, version: str) -> dict:
    """Update SemVer and increment the native build locally; never tag or publish automatically."""
    root = _project(project)
    if not re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", version):
        raise ValueError("Version must be canonical SemVer")
    path = root / "infra/mobile/release.json"
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError("Release configuration escapes project")
    release = json.loads(path.read_text())
    if tuple(map(int, version.split("."))) < tuple(
        map(int, release["version"].split("."))
    ):
        raise ValueError("Version cannot go backwards")
    release["version"] = version
    release["androidBuild"] += 1
    if release["androidBuild"] > 2100000000:
        raise ValueError("Android build number exhausted")
    path.write_text(json.dumps(release, indent=2) + "\n")
    return {
        "project": project,
        "version": version,
        "build": release["androidBuild"],
        "state": "local-changes",
        "nextStep": "Validate, commit and build before authorized publication.",
    }


@mcp.tool(annotations=READ)
def mobile_sdk_plan(project: str) -> dict:
    """Compare the shared session SDK with one consumer, without overwriting custom code."""
    root = _project(project)
    available = json.loads((ENGINE.parent / "sdk/manifest.json").read_text())
    lock = root / "infra/mobile/core-lock.json"
    current = json.loads(lock.read_text()) if lock.exists() else None
    return {
        "project": project,
        "available": available,
        "installed": current,
        "updateAvailable": current != available,
        "nextStep": "Update SDK, run tests, commit, rebuild and publish each native consumer.",
    }


@mcp.tool(annotations=WRITE)
def update_mobile_sdk(project: str) -> dict:
    """Apply a versioned shared SDK update locally; preserve custom edits and never publish automatically."""
    import hashlib

    root = _project(project)
    sdk = ENGINE.parent / "sdk"
    manifest = json.loads((sdk / "manifest.json").read_text())
    content = (sdk / "index.ts").read_bytes()
    if hashlib.sha256(content).hexdigest() != manifest["sha256"]:
        raise ValueError("SDK digest mismatch")
    target = root / "packages/mobile-core/index.ts"
    lock = root / "infra/mobile/core-lock.json"
    if (
        target.is_symlink()
        or lock.is_symlink()
        or not target.resolve().is_relative_to(root)
        or not lock.resolve().is_relative_to(root)
    ):
        raise ValueError("Consumer path escapes project")
    if target.exists():
        if not lock.exists():
            raise ValueError("Existing SDK must be enrolled and reviewed before update")
        previous = json.loads(lock.read_text())
        if hashlib.sha256(target.read_bytes()).hexdigest() != previous["sha256"]:
            raise ValueError("Consumer has custom changes; merge them explicitly")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    lock.write_text(json.dumps(manifest, indent=2) + "\n")
    return {
        "project": project,
        "version": manifest["version"],
        "state": "local-changes",
        "requires": [
            "tests",
            "commit",
            "build",
            "runtime-validation",
            "authorized-publication",
        ],
    }


@mcp.resource("mobile-pipeline://contract")
def contract() -> str:
    return json.dumps(
        {
            "version": 1,
            "commands": ["status", "build", "publish"],
            "requiredFiles": ["infra/mobile/project.json", "infra/mobile/release.json"],
            "nativeUpdates": "Versioned promotion and rebuild",
            "stores": "Android APK catalog is separate from Play and App Store publication",
        }
    )


if __name__ == "__main__":
    mcp.run()
