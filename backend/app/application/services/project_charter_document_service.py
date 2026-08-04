from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import html
import json
from pathlib import Path
import re
import shutil

import yaml

from backend.app.domain.entities.project_management import (
    PROJECT_CHARTER_BRAND_PATH,
    PROJECT_CHARTER_CHANGELOG_PATH,
    PROJECT_CHARTER_METADATA_PATH,
    PROJECT_CHARTER_RENDER_MANIFEST_PATH,
    PROJECT_CHARTER_RENDER_PATH,
    PROJECT_CHARTER_SOURCE_PATH,
    PROJECT_CHARTER_STANDARD_ID,
    ProjectCharterDocumentState,
    ProjectCharterValidationIssue,
    ProjectCharterValidationResult,
    ProjectCharterValidationSeverity,
    ProjectCharterVersionImpact,
    recommend_delivered_version_impact,
)


PLACEHOLDER_PATTERN = re.compile(
    r"\b(todo|lorem ipsum|placeholder|generated deterministic baseline)\b",
    re.IGNORECASE,
)
PROJECT_CHARTER_RENDERER_VERSION = "charter-markdown-html/v1"


@dataclass(frozen=True, slots=True)
class ProjectCharterRenderedHtml:
    html: str
    source_hash: str
    render_hash: str


@dataclass(frozen=True, slots=True)
class ProjectCharterDraftUpdateResult:
    source_path: str
    source_hash: str
    metadata_path: str
    delivered_version: str | None
    latest_release: str | None


@dataclass(frozen=True, slots=True)
class ProjectCharterReleaseResult:
    ok: bool
    version: str
    release_path: str | None
    validation: ProjectCharterValidationResult
    recommended_impact: ProjectCharterVersionImpact


@dataclass(frozen=True, slots=True)
class ProjectCharterPdfExportResult:
    ok: bool
    status: str
    message: str
    output_path: str | None
    validation: ProjectCharterValidationResult


class ProjectCharterDocumentService:
    def __init__(self, *, workspace_root: str | Path) -> None:
        self._root = Path(workspace_root).expanduser().resolve()

    def validate(self, *, client_export: bool = True) -> ProjectCharterValidationResult:
        issues: list[ProjectCharterValidationIssue] = []
        source_path = self._path(PROJECT_CHARTER_SOURCE_PATH)
        metadata_path = self._path(PROJECT_CHARTER_METADATA_PATH)
        brand_path = self._path(PROJECT_CHARTER_BRAND_PATH)
        render_manifest_path = self._path(PROJECT_CHARTER_RENDER_MANIFEST_PATH)

        source = self._read_required_text(
            source_path,
            PROJECT_CHARTER_SOURCE_PATH,
            issues,
        )
        metadata = self._read_required_yaml(
            metadata_path,
            PROJECT_CHARTER_METADATA_PATH,
            issues,
        )
        brand = self._read_required_yaml(
            brand_path,
            PROJECT_CHARTER_BRAND_PATH,
            issues,
        )

        if isinstance(metadata, dict):
            self._validate_metadata(metadata, issues)
        if isinstance(brand, dict):
            self._validate_brand(brand, issues, client_export=client_export)
        if source is not None:
            self._validate_source_text(source, issues)
        if source is not None and isinstance(metadata, dict):
            self._validate_source_hash(source, metadata, issues)
        if render_manifest_path.exists() and source is not None:
            render_manifest = self._read_json_file(
                render_manifest_path,
                PROJECT_CHARTER_RENDER_MANIFEST_PATH,
                issues,
            )
            if isinstance(render_manifest, dict):
                self._validate_render_manifest(source, metadata, render_manifest, issues)

        return ProjectCharterValidationResult(
            issues=tuple(issues),
            generated_at=_now_iso(),
        )

    def update_current_charter(
        self,
        content: str,
        *,
        changed_fields: set[str] | frozenset[str] = frozenset(),
    ) -> ProjectCharterDraftUpdateResult:
        source_path = self._path(PROJECT_CHARTER_SOURCE_PATH)
        metadata_path = self._path(PROJECT_CHARTER_METADATA_PATH)
        manifest_path = self._path(".codex/project.yaml")
        metadata = self._load_yaml(metadata_path)
        manifest = self._load_yaml(manifest_path) if manifest_path.exists() else {}
        source_path.write_text(content, encoding="utf-8")
        source_hash = _sha256_text(content)
        metadata = _metadata_with_hash(metadata, source_hash)
        metadata["status"] = ProjectCharterDocumentState.DRAFT.value
        timestamps = _ensure_mapping(metadata, "timestamps")
        timestamps["updated_at"] = _now_iso()
        field_sources = _ensure_mapping(metadata, "field_sources")
        for field in sorted(changed_fields):
            field_sources[field] = {
                "source": "draft_edit",
                "confidence": 1.0,
                "notes": "Updated through Project Charter draft edit.",
            }
        self._write_yaml(metadata_path, metadata)
        latest_release = _manifest_latest_release(manifest)
        return ProjectCharterDraftUpdateResult(
            source_path=PROJECT_CHARTER_SOURCE_PATH,
            source_hash=source_hash,
            metadata_path=PROJECT_CHARTER_METADATA_PATH,
            delivered_version=_metadata_delivered_version(metadata),
            latest_release=latest_release,
        )

    def refresh_render(self) -> ProjectCharterRenderedHtml:
        source_path = self._path(PROJECT_CHARTER_SOURCE_PATH)
        source = source_path.read_text(encoding="utf-8")
        rendered = render_charter_markdown_to_html(source)
        render_path = self._path(PROJECT_CHARTER_RENDER_PATH)
        render_path.write_text(rendered.html, encoding="utf-8")
        validation = _without_render_freshness_issues(
            self.validate(client_export=False)
        )
        manifest = build_charter_render_manifest(
            source_hash=rendered.source_hash,
            render_hash=rendered.render_hash,
            generated_at=_now_iso(),
            validation=validation,
        )
        self._path(PROJECT_CHARTER_RENDER_MANIFEST_PATH).write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        metadata_path = self._path(PROJECT_CHARTER_METADATA_PATH)
        metadata = self._load_yaml(metadata_path)
        metadata = _metadata_with_hash(metadata, rendered.source_hash)
        hashes = _ensure_mapping(metadata, "hashes")
        hashes["render"] = rendered.render_hash
        timestamps = _ensure_mapping(metadata, "timestamps")
        timestamps["updated_at"] = _now_iso()
        self._write_yaml(metadata_path, metadata)
        return rendered

    def validate_export(self) -> ProjectCharterValidationResult:
        validation = self.validate(client_export=True)
        issues = list(validation.issues)
        source_path = self._path(PROJECT_CHARTER_SOURCE_PATH)
        render_path = self._path(PROJECT_CHARTER_RENDER_PATH)
        render_manifest_path = self._path(PROJECT_CHARTER_RENDER_MANIFEST_PATH)
        if not render_path.is_file():
            issues.append(
                _issue(
                    code="missing_render_output",
                    field="render",
                    message="Rendered charter HTML is missing.",
                    next_action="Refresh the charter render before client export.",
                    affected_file=PROJECT_CHARTER_RENDER_PATH,
                )
            )
        if not render_manifest_path.is_file():
            issues.append(
                _issue(
                    code="missing_render_manifest",
                    field="render_manifest",
                    message="Rendered charter manifest is missing.",
                    next_action="Refresh the charter render before client export.",
                    affected_file=PROJECT_CHARTER_RENDER_MANIFEST_PATH,
                )
            )
        if render_path.is_file() and render_manifest_path.is_file():
            render_manifest = json.loads(
                render_manifest_path.read_text(encoding="utf-8")
            )
            source = source_path.read_text(encoding="utf-8")
            current_source_hash = _sha256_text(source)
            current_render_hash = _sha256_text(
                render_path.read_text(encoding="utf-8")
            )
            if render_manifest.get("source_hash") != current_source_hash:
                issues.append(
                    _issue(
                        code="stale_render",
                        field="render_manifest.source_hash",
                        message="Rendered charter is stale relative to acta.md.",
                        next_action="Refresh the charter render before export.",
                        affected_file=PROJECT_CHARTER_RENDER_MANIFEST_PATH,
                    )
                )
            if render_manifest.get("render_hash") != current_render_hash:
                issues.append(
                    _issue(
                        code="render_output_hash_mismatch",
                        field="render_manifest.render_hash",
                        message="Rendered charter hash does not match render.html.",
                        next_action="Refresh the charter render before export.",
                        affected_file=PROJECT_CHARTER_RENDER_MANIFEST_PATH,
                    )
                )
        return ProjectCharterValidationResult(
            issues=tuple(issues),
            generated_at=_now_iso(),
        )

    def export_pdf(self) -> ProjectCharterPdfExportResult:
        validation = self.validate_export()
        return ProjectCharterPdfExportResult(
            ok=False,
            status="unavailable",
            message=(
                "PDF export backend is not configured. Markdown remains the "
                "source of truth and render.html is the current preview artifact."
            ),
            output_path=None,
            validation=validation,
        )

    def recommend_release_impact(
        self,
        changed_fields: set[str] | frozenset[str],
    ) -> ProjectCharterVersionImpact:
        return recommend_delivered_version_impact(changed_fields)

    def release(
        self,
        version: str,
        *,
        changed_fields: set[str] | frozenset[str] = frozenset(),
        changelog_entry: str | None = None,
        client_export: bool = True,
    ) -> ProjectCharterReleaseResult:
        recommended = self.recommend_release_impact(changed_fields)
        release_dir = self._path(
            f"docs/project-management/acta/releases/{version}",
        )
        validation_issues: list[ProjectCharterValidationIssue] = []
        if release_dir.exists():
            validation_issues.append(
                _issue(
                    code="release_already_exists",
                    field="version",
                    message=f"Release {version} already exists and is immutable.",
                    next_action="Choose a new delivered version.",
                    affected_file=str(release_dir.relative_to(self._root)),
                )
            )
        if self._prior_delivered_exists() and changed_fields and not changelog_entry:
            validation_issues.append(
                _issue(
                    code="missing_changelog_entry",
                    field="changelog",
                    message="A changelog entry is required after a prior delivered version.",
                    next_action="Provide a changelog entry before releasing.",
                    affected_file=PROJECT_CHARTER_CHANGELOG_PATH,
                )
            )
        validation = (
            self.validate_export()
            if client_export
            else self.validate(client_export=False)
        )
        validation_issues.extend(validation.issues)
        if validation_issues:
            return ProjectCharterReleaseResult(
                ok=False,
                version=version,
                release_path=None,
                validation=ProjectCharterValidationResult(
                    issues=tuple(validation_issues),
                    generated_at=_now_iso(),
                ),
                recommended_impact=recommended,
            )

        source_path = self._path(PROJECT_CHARTER_SOURCE_PATH)
        delivered_source = _source_marked_delivered(
            source_path.read_text(encoding="utf-8"),
            version,
        )
        source_path.write_text(delivered_source, encoding="utf-8")
        source_hash = _sha256_text(delivered_source)
        metadata_path = self._path(PROJECT_CHARTER_METADATA_PATH)
        metadata = _metadata_with_hash(self._load_yaml(metadata_path), source_hash)
        metadata["status"] = ProjectCharterDocumentState.CLIENT_DELIVERED.value
        versions = _ensure_mapping(metadata, "versions")
        versions["delivered"] = version
        timestamps = _ensure_mapping(metadata, "timestamps")
        timestamps["updated_at"] = _now_iso()
        timestamps["delivered_at"] = timestamps["updated_at"]
        self._write_yaml(metadata_path, metadata)
        self.refresh_render()
        self._mark_delivered(version, source_hash)

        if changelog_entry:
            self._append_changelog(version, changelog_entry)
        release_dir.mkdir(parents=True, exist_ok=False)
        self._copy_release_file(PROJECT_CHARTER_SOURCE_PATH, release_dir / "acta.md")
        self._copy_release_file(
            PROJECT_CHARTER_METADATA_PATH,
            release_dir / "metadata.yaml",
        )
        if self._path(PROJECT_CHARTER_RENDER_PATH).is_file():
            self._copy_release_file(PROJECT_CHARTER_RENDER_PATH, release_dir / "render.html")
        pdf_path = self._path("docs/project-management/acta/current/acta.pdf")
        if pdf_path.is_file():
            shutil.copyfile(pdf_path, release_dir / "acta.pdf")
        (release_dir / "source-hash.txt").write_text(
            source_hash + "\n",
            encoding="utf-8",
        )
        release_manifest = {
            "version": version,
            "standard": PROJECT_CHARTER_STANDARD_ID,
            "source_hash": source_hash,
            "created_at": _now_iso(),
            "recommended_impact": recommended.value,
            "changed_fields": sorted(changed_fields),
        }
        (release_dir / "release-manifest.json").write_text(
            json.dumps(release_manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return ProjectCharterReleaseResult(
            ok=True,
            version=version,
            release_path=str(release_dir.relative_to(self._root)),
            validation=ProjectCharterValidationResult(
                issues=(),
                generated_at=_now_iso(),
            ),
            recommended_impact=recommended,
        )

    def _validate_metadata(
        self,
        metadata: dict[str, object],
        issues: list[ProjectCharterValidationIssue],
    ) -> None:
        if metadata.get("standard") != PROJECT_CHARTER_STANDARD_ID:
            issues.append(
                _issue(
                    code="invalid_standard",
                    field="standard",
                    message="Project charter metadata standard is invalid.",
                    next_action="Regenerate metadata with project-charter/v1.",
                    affected_file=PROJECT_CHARTER_METADATA_PATH,
                )
            )
        for field_path in (
            "document.title",
            "document.source_path",
            "project.name",
            "status",
            "versions.draft",
            "hashes.source",
        ):
            if _nested_value(metadata, field_path) in {None, ""}:
                issues.append(
                    _issue(
                        code="missing_metadata_field",
                        field=field_path,
                        message=f"Missing required charter metadata field {field_path}.",
                        next_action="Restore the required metadata field.",
                        affected_file=PROJECT_CHARTER_METADATA_PATH,
                    )
                )
        status = str(metadata.get("status") or "")
        valid_statuses = {state.value for state in ProjectCharterDocumentState}
        if status and status not in valid_statuses:
            issues.append(
                _issue(
                    code="invalid_status",
                    field="status",
                    message=f"Invalid charter document status: {status}.",
                    next_action="Use a valid charter status.",
                    affected_file=PROJECT_CHARTER_METADATA_PATH,
                )
            )

    def _validate_brand(
        self,
        brand: dict[str, object],
        issues: list[ProjectCharterValidationIssue],
        *,
        client_export: bool,
    ) -> None:
        logo_status = str(brand.get("logo_status") or "")
        logo_source = str(brand.get("logo_source") or "")
        if logo_status not in {"provided", "generated", "pending", "not_required"}:
            issues.append(
                _issue(
                    code="invalid_logo_status",
                    field="logo_status",
                    message="Brand logo status is missing or invalid.",
                    next_action="Set logo_status to provided, generated, pending, or not_required.",
                    affected_file=PROJECT_CHARTER_BRAND_PATH,
                )
            )
        if logo_source not in {"user_upload", "generated", "none"}:
            issues.append(
                _issue(
                    code="invalid_logo_source",
                    field="logo_source",
                    message="Brand logo source is missing or invalid.",
                    next_action="Set logo_source to user_upload, generated, or none.",
                    affected_file=PROJECT_CHARTER_BRAND_PATH,
                )
            )
        if (
            client_export
            and brand.get("client_pdf_requires_logo") is True
            and logo_status == "pending"
        ):
            issues.append(
                _issue(
                    code="required_logo_pending",
                    field="logo_status",
                    message="Client export requires a logo but the logo decision is pending.",
                    next_action="Provide, generate, or explicitly waive the logo requirement.",
                    affected_file=PROJECT_CHARTER_BRAND_PATH,
                )
            )

    def _validate_source_text(
        self,
        source: str,
        issues: list[ProjectCharterValidationIssue],
    ) -> None:
        if "Historial de revisiones" not in source:
            issues.append(
                _issue(
                    code="missing_revision_history",
                    field="revision_history",
                    message="The charter source is missing revision history.",
                    next_action="Restore the revision history section.",
                    affected_file=PROJECT_CHARTER_SOURCE_PATH,
                )
            )
        if PLACEHOLDER_PATTERN.search(source):
            issues.append(
                _issue(
                    code="placeholder_marker",
                    field="source",
                    message="The charter contains a client-visible placeholder marker.",
                    next_action="Replace generic placeholder text before client export.",
                    affected_file=PROJECT_CHARTER_SOURCE_PATH,
                )
            )

    def _validate_source_hash(
        self,
        source: str,
        metadata: dict[str, object],
        issues: list[ProjectCharterValidationIssue],
    ) -> None:
        expected = _nested_value(metadata, "hashes.source")
        actual = _sha256_text(source)
        if expected and expected != actual:
            issues.append(
                _issue(
                    code="source_hash_mismatch",
                    field="hashes.source",
                    message="Charter source hash does not match metadata.",
                    next_action="Refresh charter metadata after source changes.",
                    affected_file=PROJECT_CHARTER_METADATA_PATH,
                )
            )

    def _validate_render_manifest(
        self,
        source: str,
        metadata: dict[str, object] | None,
        render_manifest: dict[str, object],
        issues: list[ProjectCharterValidationIssue],
    ) -> None:
        source_hash = _sha256_text(source)
        render_source_hash = render_manifest.get("source_hash")
        if render_source_hash and render_source_hash != source_hash:
            issues.append(
                _issue(
                    code="stale_render",
                    field="render_manifest.source_hash",
                    message="Render manifest source hash is stale.",
                    next_action="Refresh the charter render before client export.",
                    affected_file=PROJECT_CHARTER_RENDER_MANIFEST_PATH,
                )
            )
        if isinstance(metadata, dict):
            metadata_render_hash = _nested_value(metadata, "hashes.render")
            manifest_render_hash = render_manifest.get("render_hash")
            if (
                metadata_render_hash
                and manifest_render_hash
                and metadata_render_hash != manifest_render_hash
            ):
                issues.append(
                    _issue(
                        code="render_hash_mismatch",
                        field="hashes.render",
                        message="Render hash does not match render manifest.",
                        next_action="Refresh render metadata before client export.",
                        affected_file=PROJECT_CHARTER_RENDER_MANIFEST_PATH,
                    )
                )

    def _read_required_text(
        self,
        path: Path,
        relative_path: str,
        issues: list[ProjectCharterValidationIssue],
    ) -> str | None:
        if not path.is_file():
            issues.append(
                _issue(
                    code="missing_required_file",
                    field=relative_path,
                    message=f"Required charter file is missing: {relative_path}.",
                    next_action="Restore the generated charter file.",
                    affected_file=relative_path,
                )
            )
            return None
        return path.read_text(encoding="utf-8")

    def _read_required_yaml(
        self,
        path: Path,
        relative_path: str,
        issues: list[ProjectCharterValidationIssue],
    ) -> dict[str, object] | None:
        if not path.is_file():
            issues.append(
                _issue(
                    code="missing_required_file",
                    field=relative_path,
                    message=f"Required charter file is missing: {relative_path}.",
                    next_action="Restore the generated charter file.",
                    affected_file=relative_path,
                )
            )
            return None
        payload = self._load_yaml(path)
        if not isinstance(payload, dict):
            issues.append(
                _issue(
                    code="invalid_yaml",
                    field=relative_path,
                    message=f"Charter YAML file must be a mapping: {relative_path}.",
                    next_action="Restore valid YAML content.",
                    affected_file=relative_path,
                )
            )
            return None
        return payload

    def _read_json_file(
        self,
        path: Path,
        relative_path: str,
        issues: list[ProjectCharterValidationIssue],
    ) -> dict[str, object] | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            issues.append(
                _issue(
                    code="invalid_json",
                    field=relative_path,
                    message=f"Charter JSON file is invalid: {relative_path}.",
                    next_action="Restore valid JSON content.",
                    affected_file=relative_path,
                )
            )
            return None
        return payload if isinstance(payload, dict) else None

    def _load_yaml(self, path: Path) -> dict[str, object]:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return payload if isinstance(payload, dict) else {}

    def _write_yaml(self, path: Path, payload: dict[str, object]) -> None:
        path.write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=False),
            encoding="utf-8",
        )

    def _copy_release_file(self, relative_path: str, target: Path) -> None:
        source = self._path(relative_path)
        if source.is_file():
            shutil.copyfile(source, target)

    def _mark_delivered(self, version: str, source_hash: str) -> None:
        metadata_path = self._path(PROJECT_CHARTER_METADATA_PATH)
        metadata = self._load_yaml(metadata_path)
        metadata = _metadata_with_hash(metadata, source_hash)
        metadata["status"] = ProjectCharterDocumentState.CLIENT_DELIVERED.value
        versions = _ensure_mapping(metadata, "versions")
        versions["delivered"] = version
        timestamps = _ensure_mapping(metadata, "timestamps")
        timestamps["updated_at"] = _now_iso()
        timestamps.setdefault("delivered_at", timestamps["updated_at"])
        self._write_yaml(metadata_path, metadata)

        manifest_path = self._path(".codex/project.yaml")
        if manifest_path.exists():
            manifest = self._load_yaml(manifest_path)
            project_management = _ensure_mapping(manifest, "project_management")
            project_management["latest_release"] = version
            self._write_yaml(manifest_path, manifest)

    def _append_changelog(self, version: str, entry: str) -> None:
        changelog_path = self._path(PROJECT_CHARTER_CHANGELOG_PATH)
        existing = changelog_path.read_text(encoding="utf-8") if changelog_path.exists() else "# Charter Changelog\n"
        changelog_path.write_text(
            existing.rstrip()
            + f"\n\n## {version}\n\n"
            + entry.strip()
            + "\n",
            encoding="utf-8",
        )

    def _prior_delivered_exists(self) -> bool:
        manifest_path = self._path(".codex/project.yaml")
        if manifest_path.exists():
            manifest = self._load_yaml(manifest_path)
            if _manifest_latest_release(manifest):
                return True
        releases = self._path("docs/project-management/acta/releases")
        return any(path.is_dir() and path.name.startswith("v") for path in releases.glob("*")) if releases.exists() else False

    def _path(self, relative_path: str) -> Path:
        raw = Path(relative_path)
        if raw.is_absolute() or ".." in raw.parts:
            raise ValueError("Project charter path must be relative and safe.")
        resolved = (self._root / raw).resolve()
        if not _is_relative_to(resolved, self._root):
            raise ValueError("Project charter path escaped workspace root.")
        return resolved


def _source_marked_delivered(source: str, version: str) -> str:
    updated = re.sub(
        r"(?m)^- Version entregada: .+$",
        f"- Version entregada: {version}",
        source,
        count=1,
    )
    updated = re.sub(
        r"(?m)^- Estado: .+$",
        "- Estado: client_delivered",
        updated,
        count=1,
    )
    release_row = (
        f"| {datetime.now(UTC).date().isoformat()} | {version} | "
        "client_delivered | Version entregada explicitamente al cliente. | "
        "Codex Project Factory | Si |"
    )
    if release_row not in updated:
        history_header = (
            "| Fecha | Version | Estado | Descripcion | Autor | Entregada |\n"
            "| --- | --- | --- | --- | --- | --- |"
        )
        if history_header in updated:
            updated = updated.replace(
                history_header,
                f"{history_header}\n{release_row}",
                1,
            )
    return updated


def _issue(
    *,
    code: str,
    field: str,
    message: str,
    next_action: str,
    affected_file: str,
) -> ProjectCharterValidationIssue:
    return ProjectCharterValidationIssue(
        severity=ProjectCharterValidationSeverity.ERROR,
        code=code,
        field=field,
        message=message,
        next_action=next_action,
        blocking=True,
        affected_file=affected_file,
    )


def render_charter_markdown_to_html(markdown: str) -> ProjectCharterRenderedHtml:
    body = _render_markdown_blocks(markdown)
    title = _document_title(markdown)
    html_text = (
        "<!doctype html>\n"
        '<html lang="es">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{html.escape(title)}</title>\n"
        f"<style>\n{_print_stylesheet()}\n</style>\n"
        "</head>\n"
        "<body>\n"
        '<main class="document-page">\n'
        '<section class="cover-block">\n'
        f'<div class="logo-slot">Logo</div>\n'
        f"<h1>{html.escape(title)}</h1>\n"
        '<p class="document-subtitle">Project Charter client document preview</p>\n'
        "</section>\n"
        f"{body}\n"
        "</main>\n"
        "</body>\n"
        "</html>\n"
    )
    return ProjectCharterRenderedHtml(
        html=html_text,
        source_hash=_sha256_text(markdown),
        render_hash=_sha256_text(html_text),
    )


def build_charter_render_manifest(
    *,
    source_hash: str,
    render_hash: str,
    generated_at: str | None,
    validation: ProjectCharterValidationResult,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "standard": PROJECT_CHARTER_STANDARD_ID,
        "source_path": PROJECT_CHARTER_SOURCE_PATH,
        "output_path": PROJECT_CHARTER_RENDER_PATH,
        "render_path": PROJECT_CHARTER_RENDER_PATH,
        "source_hash": source_hash,
        "render_hash": render_hash,
        "renderer": PROJECT_CHARTER_RENDERER_VERSION,
        "generated_at": generated_at,
        "status": "rendered" if validation.ok else "rendered_with_blockers",
        "validation": {
            "ok": validation.ok,
            "blocking_issue_count": len(validation.blocking_issues),
        },
    }


def _render_markdown_blocks(markdown: str) -> str:
    lines = markdown.splitlines()
    rendered: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index].rstrip()
        stripped = line.strip()
        if not stripped:
            index += 1
            continue
        if stripped.startswith("|"):
            table_lines: list[str] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_lines.append(lines[index].strip())
                index += 1
            rendered.append(_render_table(table_lines))
            continue
        if stripped.startswith("- "):
            items: list[str] = []
            while index < len(lines) and lines[index].strip().startswith("- "):
                items.append(lines[index].strip()[2:].strip())
                index += 1
            rendered.append(
                "<ul>\n"
                + "\n".join(f"<li>{_inline_markdown(item)}</li>" for item in items)
                + "\n</ul>"
            )
            continue
        ordered_match = re.match(r"^\d+\.\s+(.*)$", stripped)
        if ordered_match:
            items = []
            while index < len(lines):
                match = re.match(r"^\d+\.\s+(.*)$", lines[index].strip())
                if match is None:
                    break
                items.append(match.group(1).strip())
                index += 1
            rendered.append(
                '<ol class="toc-list">\n'
                + "\n".join(f"<li>{_inline_markdown(item)}</li>" for item in items)
                + "\n</ol>"
            )
            continue
        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            level = min(len(heading.group(1)), 4)
            text = _inline_markdown(heading.group(2))
            rendered.append(f'<h{level} class="section-heading">{text}</h{level}>')
            index += 1
            continue
        paragraph_lines = [stripped]
        index += 1
        while index < len(lines):
            candidate = lines[index].strip()
            if (
                not candidate
                or candidate.startswith(("#", "- ", "|"))
                or re.match(r"^\d+\.\s+", candidate)
            ):
                break
            paragraph_lines.append(candidate)
            index += 1
        rendered.append(
            "<p>" + _inline_markdown(" ".join(paragraph_lines)) + "</p>"
        )
    return "\n".join(rendered)


def _render_table(lines: list[str]) -> str:
    rows = [_table_cells(line) for line in lines]
    filtered = [
        row
        for row in rows
        if row and not all(set(cell) <= {"-"} for cell in row if cell)
    ]
    if not filtered:
        return ""
    header = filtered[0]
    body = filtered[1:]
    head_html = (
        "<thead><tr>"
        + "".join(f"<th>{_inline_markdown(cell)}</th>" for cell in header)
        + "</tr></thead>"
    )
    body_html = (
        "<tbody>"
        + "".join(
            "<tr>"
            + "".join(f"<td>{_inline_markdown(cell)}</td>" for cell in row)
            + "</tr>"
            for row in body
        )
        + "</tbody>"
    )
    return f"<table>{head_html}{body_html}</table>"


def _table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _inline_markdown(value: str) -> str:
    escaped = html.escape(value, quote=True)
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)


def _document_title(markdown: str) -> str:
    for line in markdown.splitlines():
        if line.startswith("# "):
            return line[2:].strip() or "Acta de Proyecto"
    return "Acta de Proyecto"


def _print_stylesheet() -> str:
    return """
@page {
  size: A4;
  margin: 18mm;
}
body {
  margin: 0;
  background: #e5e7eb;
  color: #111827;
  font-family: Arial, Helvetica, sans-serif;
  line-height: 1.5;
}
.document-page {
  width: min(210mm, calc(100vw - 32px));
  min-height: 297mm;
  margin: 24px auto;
  padding: 22mm 18mm;
  background: #ffffff;
  box-shadow: 0 12px 34px rgba(15, 23, 42, 0.16);
  box-sizing: border-box;
}
.cover-block {
  border-bottom: 2px solid #111827;
  margin-bottom: 28px;
  padding-bottom: 20px;
}
.logo-slot {
  width: 86px;
  height: 56px;
  border: 1px solid #9ca3af;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 16px;
  font-size: 11px;
  text-transform: uppercase;
  color: #4b5563;
}
.document-subtitle {
  color: #4b5563;
}
.section-heading {
  break-after: avoid;
  margin-top: 22px;
}
.toc-list {
  padding-left: 24px;
}
table {
  width: 100%;
  border-collapse: collapse;
  margin: 14px 0;
}
th,
td {
  border: 1px solid #d1d5db;
  padding: 8px;
  text-align: left;
  vertical-align: top;
}
th {
  background: #f3f4f6;
}
code {
  background: #f3f4f6;
  padding: 1px 4px;
}
@media print {
  body {
    background: #ffffff;
  }
  .document-page {
    width: auto;
    min-height: auto;
    margin: 0;
    padding: 0;
    box-shadow: none;
  }
}
""".strip()


def _metadata_with_hash(
    metadata: dict[str, object],
    source_hash: str,
) -> dict[str, object]:
    hashes = _ensure_mapping(metadata, "hashes")
    hashes["source"] = source_hash
    return metadata


def _without_render_freshness_issues(
    validation: ProjectCharterValidationResult,
) -> ProjectCharterValidationResult:
    ignored = {
        "stale_render",
        "render_hash_mismatch",
        "render_output_hash_mismatch",
    }
    return ProjectCharterValidationResult(
        issues=tuple(issue for issue in validation.issues if issue.code not in ignored),
        generated_at=validation.generated_at,
    )


def _ensure_mapping(parent: dict[str, object], key: str) -> dict[str, object]:
    value = parent.get(key)
    if not isinstance(value, dict):
        value = {}
        parent[key] = value
    return value


def _nested_value(payload: dict[str, object], dotted_path: str) -> object:
    current: object = payload
    for part in dotted_path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _metadata_delivered_version(metadata: dict[str, object]) -> str | None:
    value = _nested_value(metadata, "versions.delivered")
    return str(value) if value else None


def _manifest_latest_release(manifest: dict[str, object]) -> str | None:
    project_management = manifest.get("project_management")
    if not isinstance(project_management, dict):
        return None
    value = project_management.get("latest_release")
    return str(value) if value else None


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
