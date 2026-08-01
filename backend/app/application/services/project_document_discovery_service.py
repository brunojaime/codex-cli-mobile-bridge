from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any

import yaml

from backend.app.application.services.project_charter_document_service import (
    ProjectCharterDocumentService,
)
from backend.app.domain.entities.project_management import (
    DEFAULT_PROJECT_MANAGEMENT_MODULES,
    PROJECT_CHARTER_BRAND_PATH,
    PROJECT_CHARTER_METADATA_PATH,
    PROJECT_CHARTER_RENDER_MANIFEST_PATH,
    PROJECT_CHARTER_RENDER_PATH,
    PROJECT_CHARTER_SOURCE_PATH,
    PROJECT_CHARTER_STANDARD_ID,
    PROJECT_MANAGEMENT_ROOT,
    ProjectManagementModuleId,
)


RELEASE_VERSION_PATTERN = re.compile(r"^v[0-9]+(?:\.[0-9]+){1,2}$")


class ProjectDocumentDiscoveryError(RuntimeError):
    pass


class ProjectDocumentWorkspaceError(ProjectDocumentDiscoveryError):
    pass


class ProjectDocumentNotFoundError(ProjectDocumentDiscoveryError):
    pass


@dataclass(frozen=True, slots=True)
class ProjectDocumentWorkspaceTarget:
    workspace: Path
    source: str
    evidence: dict[str, object]


class ProjectDocumentDiscoveryService:
    def __init__(
        self,
        *,
        projects_root: str | Path,
        workspace_aliases: dict[str, str] | None = None,
        project_factory_service: Any | None = None,
        project_factory_init_service: Any | None = None,
        render_max_bytes: int = 512_000,
    ) -> None:
        self._projects_root = Path(projects_root).expanduser().resolve()
        self._workspace_aliases = {
            key: Path(value).expanduser().resolve()
            for key, value in (workspace_aliases or {}).items()
            if key.strip() and str(value).strip()
        }
        self._project_factory_service = project_factory_service
        self._project_factory_init_service = project_factory_init_service
        self._render_max_bytes = render_max_bytes

    def list_documents(
        self,
        *,
        workspace_path: str | None = None,
        draft_id: str | None = None,
        job_id: str | None = None,
    ) -> dict[str, object]:
        target = self.resolve_workspace(
            workspace_path=workspace_path,
            draft_id=draft_id,
            job_id=job_id,
        )
        modules = [self._module_payload(target.workspace, module_id) for module_id in ProjectManagementModuleId]
        charter = self._charter_summary(target.workspace)
        return {
            "kind": "codex.projectDocuments",
            "version": 1,
            "workspace_path": str(target.workspace),
            "workspace_name": target.workspace.name,
            "standard": PROJECT_CHARTER_STANDARD_ID,
            "root": PROJECT_MANAGEMENT_ROOT,
            "source": target.source,
            "evidence": target.evidence,
            "modules": modules,
            "charter": charter,
        }

    def charter_detail(
        self,
        *,
        workspace_path: str | None = None,
        draft_id: str | None = None,
        job_id: str | None = None,
        include_render_content: bool = True,
    ) -> dict[str, object]:
        target = self.resolve_workspace(
            workspace_path=workspace_path,
            draft_id=draft_id,
            job_id=job_id,
        )
        service = ProjectCharterDocumentService(workspace_root=target.workspace)
        validation = service.validate(client_export=False)
        metadata = self._read_yaml_mapping(target.workspace, PROJECT_CHARTER_METADATA_PATH)
        render_manifest = self._read_json_mapping(
            target.workspace,
            PROJECT_CHARTER_RENDER_MANIFEST_PATH,
        )
        return {
            "kind": "codex.projectDocumentCharter",
            "version": 1,
            "workspace_path": str(target.workspace),
            "workspace_name": target.workspace.name,
            "standard": PROJECT_CHARTER_STANDARD_ID,
            "source": target.source,
            "evidence": target.evidence,
            "metadata": metadata,
            "brand": self._read_yaml_mapping(target.workspace, PROJECT_CHARTER_BRAND_PATH),
            "source_summary": self._source_summary(target.workspace),
            "render": self._render_payload(
                target.workspace,
                include_content=include_render_content,
            ),
            "render_manifest": render_manifest,
            "validation": validation.to_payload(),
            "latest_release": self._latest_release(target.workspace, metadata),
        }

    def validate_charter(
        self,
        *,
        workspace_path: str | None = None,
        draft_id: str | None = None,
        job_id: str | None = None,
        client_export: bool = True,
    ) -> dict[str, object]:
        target = self.resolve_workspace(
            workspace_path=workspace_path,
            draft_id=draft_id,
            job_id=job_id,
        )
        validation = ProjectCharterDocumentService(
            workspace_root=target.workspace,
        ).validate(client_export=client_export)
        return {
            "kind": "codex.projectDocumentCharterValidation",
            "version": 1,
            "workspace_path": str(target.workspace),
            "validation": validation.to_payload(),
        }

    def render_charter(
        self,
        *,
        workspace_path: str | None = None,
        draft_id: str | None = None,
        job_id: str | None = None,
    ) -> dict[str, object]:
        target = self.resolve_workspace(
            workspace_path=workspace_path,
            draft_id=draft_id,
            job_id=job_id,
        )
        service = ProjectCharterDocumentService(workspace_root=target.workspace)
        rendered = service.refresh_render()
        manifest = self._read_json_mapping(
            target.workspace,
            PROJECT_CHARTER_RENDER_MANIFEST_PATH,
        )
        return {
            "kind": "codex.projectDocumentCharterRender",
            "version": 1,
            "workspace_path": str(target.workspace),
            "render": {
                "path": PROJECT_CHARTER_RENDER_PATH,
                "exists": True,
                "source_hash": rendered.source_hash,
                "render_hash": rendered.render_hash,
                "size_bytes": len(rendered.html.encode("utf-8")),
            },
            "render_manifest": manifest,
        }

    def release_charter(
        self,
        *,
        version: str,
        workspace_path: str | None = None,
        draft_id: str | None = None,
        job_id: str | None = None,
        changed_fields: set[str] | frozenset[str] = frozenset(),
        changelog_entry: str | None = None,
        client_export: bool = True,
    ) -> dict[str, object]:
        target = self.resolve_workspace(
            workspace_path=workspace_path,
            draft_id=draft_id,
            job_id=job_id,
        )
        normalized_version = self._validate_release_version(version)
        service = ProjectCharterDocumentService(workspace_root=target.workspace)
        result = service.release(
            normalized_version,
            changed_fields=changed_fields,
            changelog_entry=changelog_entry,
            client_export=client_export,
        )
        return {
            "kind": "codex.projectDocumentCharterRelease",
            "version": 1,
            "workspace_path": str(target.workspace),
            "ok": result.ok,
            "release_version": result.version,
            "release_path": result.release_path,
            "recommended_impact": result.recommended_impact.value,
            "validation": result.validation.to_payload(),
        }

    def list_charter_releases(
        self,
        *,
        workspace_path: str | None = None,
        draft_id: str | None = None,
        job_id: str | None = None,
    ) -> dict[str, object]:
        target = self.resolve_workspace(
            workspace_path=workspace_path,
            draft_id=draft_id,
            job_id=job_id,
        )
        releases_root = self._safe_path(
            target.workspace,
            "docs/project-management/acta/releases",
        )
        releases = []
        if releases_root.is_dir():
            for path in sorted(releases_root.iterdir(), key=lambda item: item.name):
                if not path.is_dir() or not RELEASE_VERSION_PATTERN.fullmatch(path.name):
                    continue
                releases.append(self._release_payload(target.workspace, path.name))
        return {
            "kind": "codex.projectDocumentCharterReleases",
            "version": 1,
            "workspace_path": str(target.workspace),
            "releases": releases,
        }

    def read_charter_release(
        self,
        release_version: str,
        *,
        workspace_path: str | None = None,
        draft_id: str | None = None,
        job_id: str | None = None,
        include_render_content: bool = False,
    ) -> dict[str, object]:
        target = self.resolve_workspace(
            workspace_path=workspace_path,
            draft_id=draft_id,
            job_id=job_id,
        )
        normalized_version = self._validate_release_version(release_version)
        releases_root = self._safe_path(
            target.workspace,
            "docs/project-management/acta/releases",
        )
        release_dir = self._safe_child(releases_root, normalized_version)
        if not release_dir.is_dir():
            raise ProjectDocumentNotFoundError(
                f"Charter release not found: {normalized_version}"
            )
        payload = self._release_payload(target.workspace, normalized_version)
        source_path = release_dir / "acta.md"
        render_path = release_dir / "render.html"
        payload["source"] = self._file_content_payload(
            target.workspace,
            source_path,
            include_content=True,
        )
        payload["render"] = self._file_content_payload(
            target.workspace,
            render_path,
            include_content=include_render_content,
        )
        return {
            "kind": "codex.projectDocumentCharterRelease",
            "version": 1,
            "workspace_path": str(target.workspace),
            "release": payload,
        }

    def workbench_documents_payload(self, workspace: Path | str) -> dict[str, object]:
        return self.list_documents(workspace_path=str(workspace))

    def resolve_workspace(
        self,
        *,
        workspace_path: str | None = None,
        draft_id: str | None = None,
        job_id: str | None = None,
    ) -> ProjectDocumentWorkspaceTarget:
        explicit = (workspace_path or "").strip()
        if explicit:
            workspace = self._validate_workspace_path(explicit)
            return ProjectDocumentWorkspaceTarget(
                workspace=workspace,
                source="workspace_path",
                evidence=self._workspace_evidence(workspace),
            )
        resolved = self._workspace_from_project_factory(draft_id=draft_id, job_id=job_id)
        if resolved is not None:
            workspace, source, evidence = resolved
            workspace = self._validate_workspace_path(str(workspace))
            return ProjectDocumentWorkspaceTarget(
                workspace=workspace,
                source=source,
                evidence={**self._workspace_evidence(workspace), **evidence},
            )
        raise ProjectDocumentWorkspaceError(
            "workspace_path, draft_id, or job_id is required."
        )

    def _validate_workspace_path(self, workspace_path: str) -> Path:
        raw_path = workspace_path.strip()
        if not raw_path:
            raise ProjectDocumentWorkspaceError("workspace_path is required.")
        alias_path = self._workspace_aliases.get(raw_path)
        candidate = alias_path if alias_path is not None else Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = self._projects_root / candidate
        resolved = candidate.resolve()
        if not self._is_allowed_workspace(resolved):
            raise ProjectDocumentWorkspaceError(
                "workspace_path must resolve under PROJECTS_ROOT or a known alias."
            )
        if not resolved.is_dir():
            raise ProjectDocumentWorkspaceError(
                "workspace_path must point to a directory."
            )
        project_management_root = self._safe_path(resolved, PROJECT_MANAGEMENT_ROOT)
        if project_management_root.exists() and not project_management_root.is_dir():
            raise ProjectDocumentWorkspaceError(
                "docs/project-management must be a directory when present."
            )
        return resolved

    def _workspace_from_project_factory(
        self,
        *,
        draft_id: str | None,
        job_id: str | None,
    ) -> tuple[Path, str, dict[str, object]] | None:
        normalized_job_id = (job_id or "").strip()
        if normalized_job_id:
            workspace = self._workspace_from_generation_job(normalized_job_id)
            if workspace is not None:
                return workspace, "project_factory_job", {"jobId": normalized_job_id}
            workspace = self._workspace_from_init_job(normalized_job_id)
            if workspace is not None:
                return workspace, "project_factory_init_job", {"jobId": normalized_job_id}
        normalized_draft_id = (draft_id or "").strip()
        if normalized_draft_id:
            workspace = self._workspace_from_generation_draft(normalized_draft_id)
            if workspace is not None:
                return (
                    workspace,
                    "project_factory_draft",
                    {"draftId": normalized_draft_id},
                )
            workspace = self._workspace_from_init_draft(normalized_draft_id)
            if workspace is not None:
                return (
                    workspace,
                    "project_factory_init_draft",
                    {"draftId": normalized_draft_id},
                )
        return None

    def _workspace_from_generation_job(self, job_id: str) -> Path | None:
        if self._project_factory_service is None:
            return None
        job = self._project_factory_service.get_job(job_id)
        project_path = getattr(job, "project_path", None) if job is not None else None
        return Path(project_path) if project_path else None

    def _workspace_from_generation_draft(self, draft_id: str) -> Path | None:
        if self._project_factory_service is None:
            return None
        for job in self._project_factory_service.list_jobs(draft_id=draft_id, limit=20):
            if isinstance(job, dict) and job.get("project_path"):
                return Path(str(job["project_path"]))
        return None

    def _workspace_from_init_job(self, job_id: str) -> Path | None:
        if self._project_factory_init_service is None:
            return None
        job = self._project_factory_init_service.get_job(job_id)
        relationships = getattr(job, "relationships", None)
        workspace_path = (
            getattr(relationships, "generated_workspace_path", None)
            if relationships is not None
            else None
        )
        return Path(workspace_path) if workspace_path else None

    def _workspace_from_init_draft(self, draft_id: str) -> Path | None:
        if self._project_factory_init_service is None:
            return None
        for job in self._project_factory_init_service.list_jobs(
            draft_id=draft_id,
            limit=20,
        ):
            relationships = getattr(job, "relationships", None)
            workspace_path = (
                getattr(relationships, "generated_workspace_path", None)
                if relationships is not None
                else None
            )
            if workspace_path:
                return Path(workspace_path)
        return None

    def _module_payload(
        self,
        workspace: Path,
        module_id: ProjectManagementModuleId,
    ) -> dict[str, object]:
        module = DEFAULT_PROJECT_MANAGEMENT_MODULES[module_id.value]
        module_path = module.path
        exists = self._safe_path(workspace, module_path).is_file()
        status = "present" if exists else "missing"
        if module_id != ProjectManagementModuleId.CHARTER and exists:
            status = "dormant"
        validation_summary: dict[str, object] | None = None
        if module_id == ProjectManagementModuleId.CHARTER:
            validation = ProjectCharterDocumentService(workspace_root=workspace).validate(
                client_export=False,
            )
            status = "ready" if validation.ok else "blocked"
            if not exists:
                status = "missing"
            validation_summary = {
                "ok": validation.ok,
                "blocking_count": len(validation.blocking_issues),
            }
        return {
            "id": module_id.value,
            "title": _module_title(module_id),
            "path": module_path,
            "exists": exists,
            "status": status,
            "load_by_default": module.load_by_default,
            "description": module.description,
            "validation": validation_summary,
        }

    def _charter_summary(self, workspace: Path) -> dict[str, object]:
        metadata = self._read_yaml_mapping(workspace, PROJECT_CHARTER_METADATA_PATH)
        validation = ProjectCharterDocumentService(workspace_root=workspace).validate(
            client_export=False,
        )
        render_manifest = self._read_json_mapping(
            workspace,
            PROJECT_CHARTER_RENDER_MANIFEST_PATH,
        )
        return {
            "path": PROJECT_CHARTER_SOURCE_PATH,
            "status": str(metadata.get("status") or "missing"),
            "latest_render": PROJECT_CHARTER_RENDER_PATH
            if self._safe_path(workspace, PROJECT_CHARTER_RENDER_PATH).is_file()
            else None,
            "latest_release": self._latest_release(workspace, metadata),
            "validation": {
                "ok": validation.ok,
                "blocking_count": len(validation.blocking_issues),
            },
            "render": {
                "path": PROJECT_CHARTER_RENDER_PATH,
                "exists": self._safe_path(workspace, PROJECT_CHARTER_RENDER_PATH).is_file(),
                "source_hash": render_manifest.get("source_hash"),
                "render_hash": render_manifest.get("render_hash"),
                "status": render_manifest.get("status") or "missing",
            },
        }

    def _source_summary(self, workspace: Path) -> dict[str, object]:
        source_path = self._safe_path(workspace, PROJECT_CHARTER_SOURCE_PATH)
        if not source_path.is_file():
            return {"path": PROJECT_CHARTER_SOURCE_PATH, "exists": False}
        content = source_path.read_text(encoding="utf-8")
        headings = [
            line.lstrip("#").strip()
            for line in content.splitlines()
            if line.startswith("#")
        ]
        return {
            "path": PROJECT_CHARTER_SOURCE_PATH,
            "exists": True,
            "title": headings[0] if headings else None,
            "size_bytes": len(content.encode("utf-8")),
            "sha256": _sha256_text(content),
            "section_headings": headings[:20],
            "excerpt": content.strip()[:500],
        }

    def _render_payload(
        self,
        workspace: Path,
        *,
        include_content: bool,
    ) -> dict[str, object]:
        return self._file_content_payload(
            workspace,
            self._safe_path(workspace, PROJECT_CHARTER_RENDER_PATH),
            include_content=include_content,
        )

    def _file_content_payload(
        self,
        workspace: Path,
        path: Path,
        *,
        include_content: bool,
    ) -> dict[str, object]:
        if not _is_relative_to(path.resolve(), workspace):
            raise ProjectDocumentWorkspaceError("Document path escaped workspace.")
        if not path.is_file():
            return {"path": path.relative_to(workspace).as_posix(), "exists": False}
        stat = path.stat()
        content: str | None = None
        truncated = False
        if include_content and stat.st_size <= self._render_max_bytes:
            content = path.read_text(encoding="utf-8", errors="replace")
        elif include_content:
            truncated = True
        return {
            "path": path.relative_to(workspace).as_posix(),
            "exists": True,
            "size_bytes": stat.st_size,
            "sha256": _sha256_text(path.read_text(encoding="utf-8", errors="replace")),
            "content": content,
            "truncated": truncated,
        }

    def _release_payload(
        self,
        workspace: Path,
        release_version: str,
    ) -> dict[str, object]:
        normalized_version = self._validate_release_version(release_version)
        releases_root = self._safe_path(
            workspace,
            "docs/project-management/acta/releases",
        )
        release_dir = self._safe_child(releases_root, normalized_version)
        manifest_path = release_dir / "release-manifest.json"
        metadata_path = release_dir / "metadata.yaml"
        return {
            "version": normalized_version,
            "path": release_dir.relative_to(workspace).as_posix(),
            "exists": release_dir.is_dir(),
            "manifest": self._read_json_file(manifest_path),
            "metadata": self._read_yaml_file(metadata_path),
            "artifacts": [
                path.name
                for path in sorted(release_dir.iterdir(), key=lambda item: item.name)
                if path.is_file()
            ]
            if release_dir.is_dir()
            else [],
        }

    def _latest_release(
        self,
        workspace: Path,
        metadata: dict[str, object],
    ) -> str | None:
        manifest = self._read_yaml_mapping(workspace, ".codex/project.yaml")
        project_management = manifest.get("project_management")
        if isinstance(project_management, dict) and project_management.get(
            "latest_release"
        ):
            return str(project_management["latest_release"])
        versions = metadata.get("versions")
        if isinstance(versions, dict) and versions.get("delivered"):
            return str(versions["delivered"])
        releases = self.list_charter_releases(workspace_path=str(workspace))["releases"]
        if releases:
            return str(releases[-1]["version"])
        return None

    def _workspace_evidence(self, workspace: Path) -> dict[str, object]:
        manifest = self._read_yaml_mapping(workspace, ".codex/project.yaml")
        preview_runtime = self._read_json_mapping(workspace, "release/preview-runtime.json")
        source_app = manifest.get("source_app") or preview_runtime.get("sourceApp")
        return {
            "workspacePath": str(workspace),
            "sourceApp": str(source_app) if source_app else None,
            "projectManifestPath": ".codex/project.yaml"
            if self._safe_path(workspace, ".codex/project.yaml").is_file()
            else None,
            "previewRuntimePath": "release/preview-runtime.json"
            if self._safe_path(workspace, "release/preview-runtime.json").is_file()
            else None,
        }

    def _is_allowed_workspace(self, path: Path) -> bool:
        if _is_relative_to(path, self._projects_root):
            return True
        return any(path == alias_path for alias_path in self._workspace_aliases.values())

    def _safe_path(self, workspace: Path, relative_path: str) -> Path:
        raw = Path(relative_path)
        if raw.is_absolute() or ".." in raw.parts:
            raise ProjectDocumentWorkspaceError("Document path must be relative and safe.")
        resolved = (workspace / raw).resolve()
        if not _is_relative_to(resolved, workspace):
            raise ProjectDocumentWorkspaceError("Document path escaped workspace.")
        return resolved

    def _safe_child(self, parent: Path, child_name: str) -> Path:
        if "/" in child_name or "\\" in child_name or ".." in Path(child_name).parts:
            raise ProjectDocumentWorkspaceError("Release path must be relative and safe.")
        resolved = (parent / child_name).resolve()
        if not _is_relative_to(resolved, parent):
            raise ProjectDocumentWorkspaceError("Release path escaped releases root.")
        return resolved

    def _validate_release_version(self, version: str) -> str:
        normalized = version.strip()
        if not RELEASE_VERSION_PATTERN.fullmatch(normalized):
            raise ProjectDocumentWorkspaceError(
                "release_version must use a safe version such as v1.0."
            )
        return normalized

    def _read_yaml_mapping(self, workspace: Path, relative_path: str) -> dict[str, object]:
        return self._read_yaml_file(self._safe_path(workspace, relative_path))

    def _read_json_mapping(self, workspace: Path, relative_path: str) -> dict[str, object]:
        return self._read_json_file(self._safe_path(workspace, relative_path))

    def _read_yaml_file(self, path: Path) -> dict[str, object]:
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except OSError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _read_json_file(self, path: Path) -> dict[str, object]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}


def _module_title(module_id: ProjectManagementModuleId) -> str:
    return {
        ProjectManagementModuleId.CHARTER: "Acta de Proyecto",
        ProjectManagementModuleId.WBS: "WBS",
        ProjectManagementModuleId.ROLES: "Roles y Responsabilidades",
        ProjectManagementModuleId.RISKS: "Riesgos",
        ProjectManagementModuleId.ALTERNATIVES: "Alternativas",
    }[module_id]


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
