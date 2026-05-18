from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "mcp-app"


def _module_name(app_id: str) -> str:
    return app_id.replace("-", "_")


def _resource_scheme(app_id: str) -> str:
    return app_id.replace("-", "_")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scaffold a repo-local MCP app for codex-cli-mobile-bridge.",
    )
    parser.add_argument(
        "app_id",
        help="Stable app identifier, for example project-catalog.",
    )
    parser.add_argument("--title", required=True, help="Human-readable app name.")
    parser.add_argument(
        "--description",
        required=True,
        help="Short app description.",
    )
    parser.add_argument(
        "--tag",
        dest="tags",
        action="append",
        default=[],
        help="Repeatable app tag.",
    )
    parser.add_argument(
        "--supports-ui",
        action="store_true",
        help="Mark the scaffold as intended for the MCP Apps UI extension.",
    )
    args = parser.parse_args()

    repo_root = Path.cwd().resolve()
    app_id = _slugify(args.app_id)
    module_name = _module_name(app_id)
    app_dir = repo_root / "mcp_apps" / module_name
    app_dir.mkdir(parents=True, exist_ok=True)

    init_path = app_dir / "__init__.py"
    if not init_path.exists():
        init_path.write_text(f'"""{args.title} MCP app."""\n', encoding="utf-8")

    preview_tool = {
        "name": "get_app_manifest",
        "arguments": {},
    }
    app_spec = {
        "app_id": app_id,
        "name": args.title,
        "description": args.description,
        "recommended_server_id": app_id,
        "transport": "stdio",
        "command": "uv",
        "args": [
            "run",
            "--project",
            "{repo_root}",
            "python",
            "-m",
            f"mcp_apps.{module_name}.server",
        ],
        "env": {
            "PROJECTS_ROOT": "{projects_root}",
        },
        "supports_ui_extension": args.supports_ui,
        "ui_entry_uri": f"ui://{app_id}/index.html" if args.supports_ui else None,
        "tags": sorted({tag.strip() for tag in args.tags if tag.strip()}),
        "preview_tool": preview_tool,
    }
    (app_dir / "app.json").write_text(
        json.dumps(app_spec, indent=2) + "\n",
        encoding="utf-8",
    )

    scheme = _resource_scheme(app_id)
    server_template = f'''from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations


_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

mcp = FastMCP(
    "{args.title}",
    instructions="{args.description}",
    json_response=True,
    log_level="WARNING",
)


@mcp.tool(
    title="Get App Manifest",
    description="Return the current scaffold metadata for this MCP app.",
    annotations=_ANNOTATIONS,
)
def get_app_manifest() -> dict[str, Any]:
    return {{
        "app_id": "{app_id}",
        "title": "{args.title}",
        "description": "{args.description}",
        "todo": [
            "Replace this manifest tool with real domain tools.",
            "Add a useful preview_tool in app.json if the frontend should show live data.",
            "Keep outputs JSON-friendly.",
        ],
    }}


@mcp.resource(
    "{scheme}://manifest",
    name="{args.title} Manifest",
    description="Static JSON manifest for the scaffolded app.",
    mime_type="application/json",
)
def manifest_resource() -> str:
    return json.dumps(get_app_manifest(), indent=2, sort_keys=True)


@mcp.prompt(
    name="use-{app_id}",
    title="Use {args.title}",
    description="Prompt template reminding the model how to use this app.",
)
def use_app_prompt() -> str:
    return (
        "Call `get_app_manifest` first, then replace the scaffold with domain-specific "
        "tools, resources, and prompts for the user's request."
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
'''
    (app_dir / "server.py").write_text(server_template, encoding="utf-8")

    print(f"Scaffolded MCP app at {app_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
