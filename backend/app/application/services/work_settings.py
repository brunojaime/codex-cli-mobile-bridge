"""Project preferences and interchangeable execution configuration strategies."""
from __future__ import annotations

import json
from typing import Protocol


class ProjectSettingStrategy(Protocol):
    key: str

    def default(self, policy: dict | None) -> bool: ...
    def apply(self, policy: dict, value: bool) -> dict: ...


class AutomaticExecutionStrategy:
    key = "automatic_execution"

    def default(self, policy):
        return bool(policy and policy.get("enabled"))

    def apply(self, policy, value):
        # Preferences never manufacture or bypass a project's delivery procedure.
        return {**policy, "enabled": value and bool(policy.get("dev_isolated"))}


class ProjectSettings:
    def __init__(self, coordinator, strategies=None):
        self.coordinator = coordinator
        self.strategies = {s.key: s for s in (strategies or [AutomaticExecutionStrategy()])}

    def values(self, db, workspace, policy):
        row = db.execute("SELECT payload FROM work_project_settings WHERE workspace=?", (workspace,)).fetchone()
        stored = json.loads(row[0]) if row else {}
        return {key: stored.get(key, strategy.default(policy)) for key, strategy in self.strategies.items()}

    def effective(self, db, policy):
        for key, value in self.values(db, policy["workspace_path"], policy).items():
            policy = self.strategies[key].apply(policy, value)
        return policy

    def overview(self):
        with self.coordinator.ledger() as db:
            policies = {r[0]: json.loads(r[1]) for r in db.execute("SELECT workspace,payload FROM work_policies")}
            projects = []
            for workspace in sorted(self.coordinator.messages.list_workspaces(), key=lambda w: (w.name.casefold(), w.path)):
                policy = policies.get(workspace.path)
                values = self.values(db, workspace.path, policy)
                enabled = values["automatic_execution"]
                ready = bool(policy and policy.get("dev_isolated"))
                status = "disabled" if not enabled else "enabled" if ready else "needs_setup"
                projects.append({"workspace_path": workspace.path, "name": workspace.name, "settings": values, "execution_status": status})
            return {"projects": projects}

    def update(self, workspace, changes):
        self.coordinator.workspace(workspace)
        if not changes or any(key not in self.strategies or type(value) is not bool for key, value in changes.items()):
            raise ValueError("Configuración de proyecto no admitida")
        with self.coordinator.ledger() as db:
            row = db.execute("SELECT payload FROM work_project_settings WHERE workspace=?", (workspace,)).fetchone()
            saved = json.loads(row[0]) if row else {}
            saved.update(changes)
            db.execute("INSERT INTO work_project_settings VALUES (?,?) ON CONFLICT(workspace) DO UPDATE SET payload=excluded.payload", (workspace, json.dumps(saved)))
            db.commit()
        return {"workspace_path": workspace, "settings": saved}
