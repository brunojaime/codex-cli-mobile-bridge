"""Find application-owned raster icons without traversing builds or dependencies."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

# Default Flutter template icons are framework branding, not application logos.
FLUTTER_TEMPLATE_ICONS = {
    "3c34e1f298d0c9ea3455d46db6b7759c8211a49e9ec6e44b635fc5c87dfb4180",
    "baccb205ae45f0b421be1657259b4943ac40c95094ab877f3bcbe12cd544dcbe",
}
RASTER = {".png", ".jpg", ".jpeg", ".webp"}


def bounded_image(root: Path, relative: str) -> Path | None:
    path = (root / relative).resolve()
    if (path.is_relative_to(root.resolve()) and path.suffix.lower() in RASTER
            and path.is_file() and path.stat().st_size <= 512 * 1024):
        if hashlib.sha256(path.read_bytes()).hexdigest() not in FLUTTER_TEMPLATE_ICONS:
            return path
    return None


def discover_project_logo(root: Path) -> Path | None:
    # Prefer icons declared by the app over unrelated screenshots/client brands.
    for directory in ["", "apps/web/static", "static", "public", "web", "frontend/web"]:
        base = root / directory
        if not base.resolve().is_relative_to(root.resolve()):
            continue
        for name in ["manifest.webmanifest", "manifest.json"]:
            manifest = base / name
            if not manifest.is_file() or manifest.stat().st_size > 65536:
                continue
            try:
                icons = json.loads(manifest.read_text()).get("icons", [])
                for icon in reversed(icons):
                    src = icon.get("src", "")
                    if not isinstance(src, str) or ":" in src or src.startswith("//"):
                        continue
                    path = bounded_image(base, src.lstrip("/"))
                    if path:
                        return path
            except (ValueError, AttributeError, TypeError, OSError):
                pass
    for directory in ["", "frontend", "frontend/mobile_app", "apps/mobile", "app", "mobile"]:
        base = root / directory
        if not base.resolve().is_relative_to(root.resolve()):
            continue
        pubspec = base / "pubspec.yaml"
        if pubspec.is_file() and pubspec.stat().st_size < 65536:
            for src in re.findall(r'^\s*image_path(?:_android)?:\s*[\'\"]?([^\s\'\"#]+)', pubspec.read_text(), re.M):
                path = bounded_image(base, src)
                if path:
                    return path
        app_json = base / "app.json"
        if app_json.is_file() and app_json.stat().st_size < 65536:
            try:
                config = json.loads(app_json.read_text())
                icon = config.get("expo", config).get("icon")
                if isinstance(icon, str):
                    path = bounded_image(base, icon)
                    if path:
                        return path
            except (ValueError, AttributeError, OSError):
                pass
        for relative in ["assets/branding/app_icon.png", "assets/brand/app_icon.png", "assets/icon.png", "assets/logo.png",
                         "web/icons/Icon-512.png", "android/app/src/main/res/mipmap-xxxhdpi/ic_launcher.png"]:
            path = bounded_image(base, relative)
            if path:
                return path
    for directory in ["apps/web/static", "static", "public", "frontend/assets", "assets"]:
        for name in ["brand/icon-512.png", "icons/icon-512.png", "icons/gestion-512.png", "brand/logo.png", "logo.png", "favicon.png"]:
            path = bounded_image(root, str(Path(directory) / name))
            if path:
                return path
    return None


def catalog_project_logo(root: Path, catalog_root: Path, *, allow_fallback: bool = False) -> Path | None:
    catalog = catalog_root / "catalog.json"
    if not catalog.is_file():
        return None
    try:
        data = json.loads(catalog.read_text())
        record = data.get("workspaces", {}).get(str(root.resolve()), {})
        if record.get("kind") == "fallback" or not record:
            if not allow_fallback:
                return None
            record = data.get("fallback", {})
        asset = record.get("asset")
        return bounded_image(catalog_root, asset) if isinstance(asset, str) else None
    except (ValueError, AttributeError, OSError):
        return None
