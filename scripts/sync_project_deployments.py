#!/usr/bin/env python3
"""Read real provider deployments into Bridge's private metadata index.

Only GET requests are issued to Cloudflare. No application repository is changed.
No branch, template, local build, or configured environment proves publication.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tomllib
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.application.services.project_deployments import (  # noqa: E402
    DeploymentIndex,
    DeploymentRecord,
    IndexedProject,
)

ALIASES = {
    "development": "dev",
    "staging": "qa",
    "production": "prod",
    "dev": "dev",
    "qa": "qa",
    "prod": "prod",
}
SKIP = {
    ".git",
    "node_modules",
    "tmp",
    ".run",
    ".private",
    "build",
    "dist",
    ".svelte-kit",
    "docs",
    "reports",
    "artifacts",
    "vendor",
    "static",
    "tests",
    "test",
    ".venv",
    ".data",
}


def git(path, *args):
    result = subprocess.run(
        ["git", *args], cwd=path, capture_output=True, text=True, timeout=15
    )
    return result.stdout if result.returncode == 0 else ""


def origin(value):
    if not isinstance(value, str):
        return None
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
    ):
        return None
    if parsed.hostname in {"localhost", "127.0.0.1", "0.0.0.0", "10.0.2.2"}:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def manifest_candidates(data, env=None):
    out = []
    if isinstance(data, dict):
        env = ALIASES.get(str(data.get("environment") or data.get("env") or env), env)
        url = next(
            (
                origin(data.get(k))
                for k in ["origin", "publicOrigin", "baseUrl"]
                if origin(data.get(k))
            ),
            None,
        )
        worker = next(
            (data[k] for k in ["worker", "workerName"] if isinstance(data.get(k), str)),
            None,
        )
        if url or worker:
            out.append({"environment": env, "origin": url, "worker": worker})
        for key, value in data.items():
            if key.lower() in {"vars", "secrets", "credentials", "tokens", "bindings"}:
                continue
            if isinstance(value, (dict, list)):
                out.extend(
                    manifest_candidates(
                        value, ALIASES.get(key, key if key == "preview" else env)
                    )
                )
    elif isinstance(data, list):
        for value in data:
            out.extend(manifest_candidates(value, env))
    return out


def jsonc(text):
    return json.loads(
        re.sub(r",\s*([}\]])", r"\1", re.sub(r"^\s*//.*$", "", text, flags=re.M))
    )


def discover(project):
    path = Path(project["workspace_path"])
    remote = git(path, "config", "--get", "remote.origin.url").strip()
    repo = (
        re.split(r"github\.com[:/]", remote)[-1].removesuffix(".git")
        if "github.com" in remote
        else None
    )
    candidates = []
    for relative in [
        "infra/environments.json",
        "environments.json",
        "deploy/environments.json",
        "config/environments.json",
    ]:
        file = path / relative
        values = (
            [file.read_text()]
            if file.is_file() and file.stat().st_size < 1024 * 1024
            else []
        )
        cached = git(path, "show", f"origin/main:{relative}")
        if cached:
            values.append(cached)
        for value in values:
            try:
                candidates.extend(manifest_candidates(json.loads(value)))
            except ValueError:
                pass
    for directory, dirs, files in os.walk(path):
        depth = len(Path(directory).relative_to(path).parts)
        dirs[:] = [
            d for d in dirs if d not in SKIP and not d.startswith(".") and depth < 4
        ]
        for name in files:
            if not name.startswith("wrangler") or not name.endswith(
                (".json", ".jsonc", ".toml")
            ):
                continue
            file = Path(directory) / name
            if file.stat().st_size > 1024 * 1024:
                continue
            try:
                data = (
                    tomllib.loads(file.read_text())
                    if name.endswith(".toml")
                    else jsonc(file.read_text())
                )
            except (ValueError, OSError):
                continue

            def config(value, label):
                env = next(
                    (
                        ALIASES[e]
                        for e in ALIASES
                        if re.search(r"(?:^|[./_-])" + e + r"(?:[./_-]|$)", label)
                    ),
                    None,
                )
                if isinstance(value.get("name"), str):
                    candidates.append(
                        {
                            "environment": env,
                            "worker": value["name"],
                            "origin": None,
                            "source": str(file.relative_to(path)),
                        }
                    )
                routes = value.get("routes", [])
                if value.get("route"):
                    routes = [*routes, value["route"]]
                for route in routes:
                    pattern = route.get("pattern") if isinstance(route, dict) else route
                    if isinstance(pattern, str):
                        url = origin(
                            ("https://" if "://" not in pattern else "")
                            + pattern.replace("/*", "").rstrip("/")
                        )
                        if url and "*" not in url:
                            candidates.append(
                                {
                                    "environment": env,
                                    "worker": value.get("name"),
                                    "origin": url,
                                    "source": str(file.relative_to(path)),
                                }
                            )
                for key, item in value.get("env", {}).items():
                    if isinstance(item, dict):
                        config(item, key)

            config(data, str(file.relative_to(path)))
    return {**project, "repo": repo, "candidates": candidates}


def worker_environment(name):
    for suffix, env in [
        ("-development", "dev"),
        ("-production", "prod"),
        ("-staging", "qa"),
        ("-dev", "dev"),
        ("-qa", "qa"),
        ("-prod", "prod"),
    ]:
        if name.endswith(suffix):
            return env
    return None


def map_workers(projects, workers, domains):
    """Use canonical manifest origins and exact worker identities, not CF's
    legacy `environment=production` (which is also returned for DEV workers)."""
    names = {w["id"] for w in workers}
    hosts = {d["hostname"]: d["service"] for d in domains}
    groups = {}
    for project in projects:
        groups.setdefault(project.get("repo") or project["workspace_path"], []).append(
            project
        )
    result = {}
    for group in groups.values():
        mapped = {}
        canonical = next(
            (p for p in group if p["name"] == (p.get("repo") or "").split("/")[-1]),
            group[0],
        )
        # Explicit business environments + real custom-domain ownership outrank old worker names.
        for project in sorted(group, key=lambda p: p is canonical):
            for candidate in project["candidates"]:
                env = ALIASES.get(str(candidate.get("environment")))
                worker = (
                    hosts.get(urlsplit(candidate["origin"]).hostname)
                    if candidate.get("origin")
                    else None
                )
                if env and worker in names:
                    mapped[env] = worker
        base = (canonical.get("repo") or canonical["name"]).split("/")[-1]
        for suffix, env in [
            ("dev", "dev"),
            ("development", "dev"),
            ("qa", "qa"),
            ("staging", "qa"),
            ("prod", "prod"),
            ("production", "prod"),
        ]:
            name = f"{base}-{suffix}"
            if name in names:
                mapped.setdefault(env, name)
        # Root/declared app worker configs (avoid unrelated mail/MCP/media components).
        for candidate in canonical["candidates"]:
            worker = candidate.get("worker")
            if worker not in names:
                continue
            source = candidate.get("source", "")
            parts = Path(source).parts
            if (
                len(parts) > 1
                and parts[0] not in {"infra", "config"}
                and not worker.startswith(base + "-")
            ):
                continue
            if worker in {"nienfos-preview-runtime", "nienfos-preview-web"}:
                continue
            if any(
                x in worker
                for x in ["-mcp", "-mail-", "-notifications-", "-media-", "-local"]
            ):
                continue
            env = ALIASES.get(str(candidate.get("environment"))) or worker_environment(
                worker
            )
            if not env:
                qa_host = any(
                    d["service"] == worker
                    and re.search(r"(^|[.-])(qa|staging)([.-]|$)", d["hostname"])
                    for d in domains
                )
                env = (
                    "qa"
                    if qa_host
                    else "dev"
                    if worker.endswith("-preview")
                    or worker.startswith("nienfos-preview-")
                    else None
                )
            if env:
                mapped.setdefault(env, worker)
        # Existing factory previews use one known worker named after the exact project.
        for name in [f"nienfos-preview-{base}", f"{base}-preview"]:
            if name in names and "dev" not in mapped and "qa" not in mapped:
                mapped["dev"] = name
        for project in group:
            result[project["workspace_path"]] = dict(mapped)
    return result


def receipt_commits(projects):
    out = {}
    seen = set()
    for p in projects:
        identity = p.get("repo") or p["workspace_path"]
        if identity in seen:
            continue
        seen.add(identity)
        for relative in ["docs/reports", "reports", "artifacts"]:
            base = Path(p["workspace_path"]) / relative
            count = 0
            for directory, dirs, files in os.walk(base):
                depth = len(Path(directory).relative_to(base).parts)
                dirs[:] = [
                    d
                    for d in dirs
                    if d not in {"node_modules", "tmp", "backups", "backup", ".private"}
                    and depth < 7
                ]
                for name in files:
                    if "deployment" not in name or not name.endswith(".json"):
                        continue
                    count += 1
                    if count > 3000:
                        break
                    file = Path(directory) / name
                    if file.stat().st_size > 512 * 1024:
                        continue
                    try:
                        data = json.loads(file.read_text())
                    except (ValueError, OSError):
                        continue
                    if (
                        not isinstance(data, dict)
                        or data.get("sourceVersionVerified") is not True
                    ):
                        continue
                    revision = data.get("revision")
                    if (
                        isinstance(revision, str)
                        and re.fullmatch("[a-f0-9]{40}", revision)
                        and isinstance(data.get("worker"), str)
                        and isinstance(data.get("deployment"), str)
                    ):
                        key = (data["worker"], data["deployment"])
                        if key in out and out[key] != revision:
                            out[key] = None
                        else:
                            out[key] = revision
    return out


def run(args):
    response = httpx.get(
        args.bridge_url.rstrip("/") + "/work/deployments", timeout=60, trust_env=False
    )
    response.raise_for_status()
    raw = response.json()["projects"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        projects = list(
            pool.map(
                discover,
                [
                    {"name": p["name"], "workspace_path": p["workspace_path"]}
                    for p in raw
                ],
            )
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    credential = tomllib.loads(args.oauth_file.read_text())
    expiry = credential.get("expiration_time")
    if (
        expiry
        and (
            datetime.fromisoformat(expiry.replace("Z", "+00:00"))
            - datetime.now(timezone.utc)
        ).total_seconds()
        < 300
    ):
        # Let the existing CLI refresh its own session. Never copy/print tokens,
        # start an interactive login, or write credentials ourselves.
        node_candidates = sorted(
            (Path.home() / ".nvm/versions/node").glob("v22.*/bin/node")
        )
        wrangler = args.wrangler_js
        if not node_candidates or not wrangler.exists():
            raise ValueError("Existing Cloudflare CLI unavailable for session refresh")
        environment = {
            k: v
            for k, v in os.environ.items()
            if k
            not in {"CLOUDFLARE_API_TOKEN", "CLOUDFLARE_API_KEY", "CLOUDFLARE_EMAIL"}
        }
        environment.update(CI="true", WRANGLER_SEND_METRICS="false")
        result = subprocess.run(
            [str(node_candidates[-1]), str(wrangler), "whoami"],
            cwd=args.output.parent,
            env=environment,
            capture_output=True,
            timeout=45,
        )
        if result.returncode:
            raise ValueError("Cloudflare session refresh unavailable")
        credential = tomllib.loads(args.oauth_file.read_text())
    token = credential.get("oauth_token")
    if not token:
        raise ValueError("Cloudflare session unavailable")
    with httpx.Client(
        base_url="https://api.cloudflare.com/client/v4",
        headers={"Authorization": "Bearer " + token},
        timeout=30,
    ) as client:

        def get(path):
            r = client.get(path)
            r.raise_for_status()
            body = r.json()
            if body.get("success") is not True:
                raise ValueError("Cloudflare read failed")
            return body["result"]

        accounts = get("/accounts")
        account = args.account_id
        if not account:
            if len(accounts) != 1:
                raise ValueError("Select Cloudflare account explicitly")
            account = accounts[0]["id"]
        prefix = f"/accounts/{account}/workers"
        workers = get(prefix + "/scripts")
        domains = get(prefix + "/domains")
        mapping = map_workers(projects, workers, domains)
        receipts = receipt_commits(projects)
        pages = get(f"/accounts/{account}/pages/projects")
        selected = sorted({w for values in mapping.values() for w in values.values()})

        def deployment(worker):
            try:
                result = get(prefix + f"/scripts/{worker}/deployments")
                rows = (
                    result.get("deployments", [])
                    if isinstance(result, dict)
                    else result
                )
                if not rows:
                    return (
                        worker,
                        None,
                        "No hay un comprobante de publicación disponible en el proveedor.",
                    )
                latest = max(rows, key=lambda r: r["created_on"])
                versions = latest.get("versions", [])
                commit = (
                    receipts.get((worker, versions[0]["version_id"]))
                    if len(versions) == 1
                    else None
                )
                message = latest.get("annotations", {}).get("workers/message", "")
                match = re.search(
                    r"(?:commit|revision|source)\s*[:=]\s*([a-f0-9]{40})(?![a-f0-9])",
                    message,
                    re.I,
                )
                if match and not commit:
                    commit = match[1].lower()
                return (
                    worker,
                    {
                        "id": f"cf:{worker}:{latest['id']}",
                        "status": "published",
                        "deployed_at": latest["created_on"],
                        "commit": commit,
                        "release": None,
                    },
                    None,
                )
            except (httpx.HTTPError, ValueError, KeyError, TypeError):
                return (
                    worker,
                    None,
                    "No se pudo verificar la última publicación en el proveedor.",
                )

        with ThreadPoolExecutor(max_workers=4) as pool:
            fetched = {
                w: (record, error)
                for w, record, error in pool.map(deployment, selected)
            }
    previous = {}
    if args.output.exists():
        old = DeploymentIndex.model_validate_json(args.output.read_bytes())
        previous = {p.workspace_path: p for p in old.projects}
    indexed = []
    audit = []
    for project in projects:
        path = project["workspace_path"]
        records = (
            {
                r.id: r
                for r in previous[path].deployments
                if (
                    r.id.startswith("cf:")
                    and r.id.split(":")[1] in mapping[path].values()
                )
                or r.id.startswith("pages:")
            }
            if path in previous
            else {}
        )
        errors = []
        states = {}
        for env, worker in mapping[path].items():
            value, error = fetched[worker]
            if error:
                errors.append(f"{env.upper()}: {error}")
                states[env] = {"worker": worker, "state": "unverified"}
            else:
                record = DeploymentRecord(environment=env, **value)
                if record.id in records and not record.commit:
                    record.commit = records[record.id].commit
                records[record.id] = record
                states[env] = {
                    "worker": worker,
                    "state": "published",
                    "deployed_at": value["deployed_at"],
                    "commit": record.commit,
                }
        if "prod" not in mapping[path]:
            base = (project.get("repo") or project["name"]).split("/")[-1]
            for page in pages:
                if page["name"] != base and base not in page.get("domains", []):
                    continue
                deploy = (
                    page.get("canonical_deployment")
                    or page.get("production_deployment")
                    or {}
                )
                if (
                    not deploy
                    or deploy.get("latest_stage", {}).get("status") != "success"
                ):
                    continue
                revision = (
                    deploy.get("deployment_trigger", {})
                    .get("metadata", {})
                    .get("commit_hash")
                )
                commit = (
                    revision
                    if isinstance(revision, str)
                    and re.fullmatch("[a-f0-9]{40}", revision)
                    else None
                )
                record = DeploymentRecord(
                    id=f"pages:{page['name']}:{deploy['id']}",
                    environment="prod",
                    status="published",
                    deployed_at=deploy["created_on"],
                    commit=commit,
                )
                records[record.id] = record
                states["prod"] = {
                    "page": page["name"],
                    "state": "published",
                    "deployed_at": deploy["created_on"],
                    "commit": commit,
                }
        values = sorted(records.values(), key=lambda r: r.deployed_at)[-900:]
        indexed.append(
            IndexedProject(workspace_path=path, deployments=values, errors=errors)
        )
        audit.append(
            {
                "name": project["name"],
                "workspace_path": path,
                "repo": project["repo"],
                "environments": states,
                "configured_candidates": len(project["candidates"]),
                "errors": errors,
            }
        )
    now = datetime.now(timezone.utc)
    index = DeploymentIndex(version=1, observed_at=now, projects=indexed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".tmp")
    temporary.write_text(index.model_dump_json(indent=2) + "\n")
    temporary.replace(args.output)
    args.audit.parent.mkdir(parents=True, exist_ok=True)
    args.audit.write_text(
        json.dumps(
            {
                "observed_at": now.isoformat(),
                "workspace_count": len(projects),
                "provider_worker_count": len(workers),
                "matched_worker_count": len(selected),
                "projects": audit,
            },
            indent=2,
        )
        + "\n"
    )
    print(
        f"Indexed {len(selected)} real workers across {len(projects)} workspaces; no application deployed or modified."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bridge-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--oauth-file",
        type=Path,
        default=Path.home() / ".config/.wrangler/config/default.toml",
    )
    parser.add_argument("--account-id")
    parser.add_argument(
        "--wrangler-js",
        type=Path,
        default=Path.home()
        / "Projects/nienfos-gestion/node_modules/wrangler/bin/wrangler.js",
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / ".data/project-deployments/index.json"
    )
    parser.add_argument(
        "--audit",
        type=Path,
        default=ROOT / "reports/project-environment-audit-20261106/inventory.json",
    )
    args = parser.parse_args()
    try:
        run(args)
    except (httpx.HTTPError, OSError, ValueError, KeyError, TypeError) as error:
        print(
            f"Deployment synchronization failed ({type(error).__name__}); previous index preserved.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
