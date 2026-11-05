"""Workspace recency uses actual execution timestamps, never session touch times."""

from pathlib import Path
from datetime import timezone


def workspaces_by_execution(workspaces, sessions, jobs):
    workspace_paths = {str(Path(w.path).resolve()) for w in workspaces}
    session_paths = {s.id: str(Path(s.workspace_path).resolve()) for s in sessions}
    latest = {}
    for job in jobs:
        path = session_paths.get(job.session_id)
        if path not in workspace_paths:
            continue
        # Queued requests have not executed yet. Failed/cancelled runs count
        # when they have activity; untouched pending requests do not.
        status = str(job.status)
        if status in {"pending", "queued"}:
            continue
        stamp = job.completed_at or job.updated_at or job.created_at
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        if path not in latest or stamp > latest[path]:
            latest[path] = stamp
    ordered = sorted(
        workspaces,
        key=lambda w: (
            -latest[str(Path(w.path).resolve())].timestamp()
            if str(Path(w.path).resolve()) in latest
            else float("inf"),
            w.name.casefold(),
            w.path,
        ),
    )
    return [(w, latest.get(str(Path(w.path).resolve()))) for w in ordered]
