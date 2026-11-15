"""Read-only, bounded projection of the objective coordinator's durable state.

Never returns prompts, command output, source documents or arbitrary filesystem
paths. Both Bridge channels observe the same owner; reads cannot start jobs.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from .team_communication import presentation


def text(value, limit=1500):
    return value[:limit] if isinstance(value, str) else ""


class ObjectiveTeamView:
    def __init__(self, root, workspaces):
        self.root = Path(root).expanduser().resolve()
        self.workspaces = {str(Path(w.path).resolve()): w.name for w in workspaces}

    def state(self, run_id):
        if not re.fullmatch(r"[a-f0-9]{24}", run_id):
            raise KeyError(run_id)
        p = self.root / "runs" / run_id / "state.json"
        if not p.resolve().is_relative_to(self.root) or p.stat().st_size > 20_000_000:
            raise ValueError("Invalid state")
        s = json.loads(p.read_text())
        workspace = str(Path(s["request"]["workspace"]).resolve())
        if s["id"] != run_id or workspace not in self.workspaces:
            raise KeyError(run_id)
        return s

    def overview(self, workspace=None):
        if workspace is not None and str(Path(workspace).resolve()) not in self.workspaces:
            raise KeyError(workspace)
        runs, unavailable = [], 0
        paths = sorted((self.root / "runs").glob("*/state.json"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        for p in paths[:200]:
            try:
                s = self.state(p.parent.name)
                if workspace and Path(s["request"]["workspace"]).resolve() != Path(workspace).resolve():
                    continue
                runs.append(self.project(s, detail=False))
            except KeyError:
                continue
            except (OSError, ValueError, TypeError):
                unavailable += 1
        return {"runs": runs, "unavailable": unavailable, "truncated": len(paths) > 200,
                "owner": "Batata · coordinador por objetivos", "read_only": True}

    def project(self, s, *, detail=True):
        units = s.get("units", [])
        workspace = str(Path(s["request"]["workspace"]).resolve())
        delivery = s.get("delivery", {})
        result = {"id": s["id"], "project": self.workspaces[workspace],
                  "objective": text(s["request"].get("objective"), 4000),
                  "status": text(s.get("status")), "updated_at": s.get("updated_at"),
                  "created_at": s.get("created_at"), "commit": text(s.get("head"), 40),
                  "calls": s.get("calls", 0), "max_calls": s["request"].get("max_calls"),
                  "accepted_units": sum(u.get("state") == "accepted" for u in units),
                  "total_units": len(units),
                  "delivery": {k: delivery.get(k) is True for k in ("implemented", "verified", "applied")},
                  "active_agents": [{"role": j.get("role"), "phase": text(j.get("runtime_phase")),
                                     "unit": j.get("unit")} for j in s.get("jobs", [])
                                    if j.get("status") in ("running", "starting", "launching", "pending")]}
        result["presentation"] = presentation(s, self.root)
        if not detail:
            return result
        blocker = s.get("external_blocker") or {}
        result["blocker"] = {k: text(blocker.get(k)) for k in ("reason", "next_action")}
        result["units"] = [{k: u.get(k) for k in ("id", "owner", "state", "stories", "depends_on")}
                           | {"objective": text(u.get("objective"))} for u in units]
        result["stories"] = []
        for story in s.get("spec", {}).get("stories", []):
            owners = [u for u in units if story["id"] in u.get("stories", [])]
            state = "accepted" if owners and all(u.get("state") == "accepted" for u in owners) else "pending"
            result["stories"].append({"id": story["id"], "role": text(story.get("role")),
                                      "priority": story.get("priority"), "state": state,
                                      "acceptance": [text(a) for a in story.get("acceptance", [])]})
        result["jobs"] = []
        for j in s.get("jobs", [])[-100:]:
            ticket = j.get("ticket") or {}
            result["jobs"].append({k: j.get(k) for k in ("role", "unit", "status", "started_at", "finished_at")}
                                  | {"phase": text(j.get("runtime_phase")),
                                     "session_id": ticket.get("session_id"),
                                     "verdict": (j.get("result") or {}).get("verdict"),
                                     "context": self.job_context(s, j)})
        result["issues"] = [{k: text(i.get(k)) for k in
                             ("id", "status", "severity", "summary", "expected", "observed", "owner", "unit")}
                            for i in s.get("issues", {}).values()]
        result["events"] = [{"type": text(e.get("type", e.get("kind"))),
                             "at": e.get("at"), "reason": text(e.get("reason"))}
                            for e in s.get("events", [])[-30:]]
        result["images"] = [{"id": key, "label": path.name, "commit": commit,
                             "reviewed": reviewed}
                            for key, path, commit, _, reviewed in self.images(s)]
        return result

    def job_context(self, s, job):
        """Only attest references present in the persisted handoff, never reads."""
        key = job.get('key', '')
        if not isinstance(key, str) or not re.fullmatch(r'[a-f0-9]{24}(?:-[0-9]+-[a-z_]+)?', key):
            return {'available': False, 'sources': [], 'reads_recorded': False}
        root = self.root / 'runs' / s['id']
        path = root / ('handoff-' + key + '.md')
        if not path.resolve().is_relative_to(root.resolve()) or not path.is_file() or path.stat().st_size > 2_000_000:
            return {'available': False, 'sources': [], 'reads_recorded': False}
        content = path.read_text()
        sources = []
        for source in s['request'].get('sources', []):
            if not isinstance(source, dict):
                continue
            location = source.get('path')
            digest = source.get('sha256', '')
            if isinstance(location, str) and location in content and re.fullmatch(r'[a-f0-9]{64}', digest):
                sources.append({'name': Path(location).name, 'sha256': digest, 'status': 'referenced'})
        return {'available': True, 'handoff_sha256': hashlib.sha256(content.encode()).hexdigest(),
                'sources': sources, 'reads_recorded': False}

    def images(self, s):
        root = self.root / "runs" / s["id"] / "evidence"
        found = {}
        for j in s.get("jobs", []):
            for item in (j.get("result") or {}).get("verified_image_files", []):
                p = Path(item.get("path", "")).resolve()
                if p.is_relative_to(root.resolve()) and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                    key = hashlib.sha256(str(p.relative_to(root)).encode()).hexdigest()[:24]
                    found[key] = (key, p, item.get("commit"), item.get("sha256"), True)
            # UX may attach proposals before independent review. Mark them as
            # such; only raster evidence inside that job's workspace is eligible.
            if j.get('role') != 'ux' or not j.get('workspace'):
                continue
            workspace = Path(j['workspace']).resolve()
            for item in (j.get('result') or {}).get('evidence', []):
                if item.get('kind') not in {'browser', 'screenshot'}:
                    continue
                p = Path(item.get('reference', ''))
                if not p.is_absolute():
                    p = workspace / p
                p = p.resolve()
                if not p.is_relative_to(workspace) or p.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp'}:
                    continue
                try:
                    if p.stat().st_size > 15_000_000:
                        continue
                    sha = hashlib.sha256(p.read_bytes()).hexdigest()
                    key = hashlib.sha256((j['key'] + str(p.relative_to(workspace))).encode()).hexdigest()[:24]
                    found[key] = (key, p, (j.get('result') or {}).get('commit', j.get('base')), sha, False)
                except OSError:
                    continue
        return list(found.values())[-60:]

    def image(self, run_id, image_id):
        s = self.state(run_id)
        for key, path, _, sha, _ in self.images(s):
            if key == image_id and path.stat().st_size <= 15_000_000:
                data = path.read_bytes()
                if hashlib.sha256(data).hexdigest() != sha:
                    raise ValueError("Evidence changed")
                if data.startswith(b"\x89PNG\r\n\x1a\n"):
                    return data, "image/png"
                if data.startswith(b"\xff\xd8\xff"):
                    return data, "image/jpeg"
                if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
                    return data, "image/webp"
        raise KeyError(image_id)
