from __future__ import annotations

import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.app.application.services.project_factory_manifest_service import (
    ProjectFactoryManifestPlan,
)
from backend.app.application.services.project_factory_reference_asset_service import (
    ProjectFactoryReferenceAsset,
    ProjectFactoryReferenceAssetService,
)


@dataclass(frozen=True, slots=True)
class ProjectFactoryGeneratedFile:
    path: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class ProjectFactoryGenerationResult:
    ok: bool
    status: str
    target_path: str
    generated_files: tuple[ProjectFactoryGeneratedFile, ...]
    git_status: str
    message: str

    def to_payload(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "status": self.status,
            "target_path": self.target_path,
            "generated_files": [
                {"path": item.path, "size_bytes": item.size_bytes}
                for item in self.generated_files
            ],
            "git_status": self.git_status,
            "message": self.message,
        }


class ProjectFactoryGeneratorError(RuntimeError):
    pass


class ProjectFactoryGeneratorService:
    def __init__(
        self,
        *,
        reference_asset_service: ProjectFactoryReferenceAssetService | None = None,
    ) -> None:
        self._reference_asset_service = reference_asset_service

    def generate(
        self,
        manifest_plan: ProjectFactoryManifestPlan,
        *,
        reference_assets: Sequence[ProjectFactoryReferenceAsset] = (),
    ) -> ProjectFactoryGenerationResult:
        if not manifest_plan.ok or not manifest_plan.target_path:
            raise ProjectFactoryGeneratorError(
                "Manifest plan must be valid before generation."
            )
        target = Path(manifest_plan.target_path).expanduser().resolve()
        if target.exists():
            raise ProjectFactoryGeneratorError(
                f"Target project already exists: {target}"
            )

        written: list[ProjectFactoryGeneratedFile] = []
        try:
            target.mkdir(parents=False)
            for relative_path, content in _project_files(manifest_plan.manifest).items():
                path = target / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                if relative_path.startswith("scripts/") and relative_path.endswith(".sh"):
                    path.chmod(0o755)
                written.append(
                    ProjectFactoryGeneratedFile(
                        path=relative_path,
                        size_bytes=path.stat().st_size,
                    )
                )
            for relative_dir in (
                "assets/reference/uploaded",
                "apps/mobile",
                "backend",
                "references/images",
            ):
                directory = target / relative_dir
                directory.mkdir(parents=True, exist_ok=True)
                gitkeep = directory / ".gitkeep"
                if not gitkeep.exists():
                    gitkeep.write_text("", encoding="utf-8")
                    written.append(
                        ProjectFactoryGeneratedFile(
                            path=str(gitkeep.relative_to(target)),
                            size_bytes=0,
                        )
                    )
            if reference_assets:
                if self._reference_asset_service is None:
                    raise ProjectFactoryGeneratorError(
                        "Reference asset service is required to copy assets."
                    )
                copied_assets = self._reference_asset_service.copy_assets_to_project(
                    assets=tuple(reference_assets),
                    target_project=target,
                )
                for relative_path in copied_assets:
                    path = target / relative_path
                    written.append(
                        ProjectFactoryGeneratedFile(
                            path=relative_path,
                            size_bytes=path.stat().st_size,
                        )
                    )
            git_status = _init_git(target)
        except Exception as exc:
            _cleanup_created_target(target)
            if isinstance(exc, ProjectFactoryGeneratorError):
                raise
            raise ProjectFactoryGeneratorError(str(exc)) from exc

        return ProjectFactoryGenerationResult(
            ok=True,
            status="ready",
            target_path=str(target),
            generated_files=tuple(sorted(written, key=lambda item: item.path)),
            git_status=git_status,
            message="Local project foundation generated.",
        )


def _project_files(manifest: dict[str, Any]) -> dict[str, str]:
    name = str(manifest["name"])
    slug = str(manifest["slug"])
    business_type = str(manifest["business_type"])
    primary_goal = str(manifest["primary_goal"])
    workflow = manifest["codex"]["creation_workflow"]
    files = {
        ".codex/project.yaml": _to_yaml(manifest),
        ".gitignore": _gitignore(),
        "README.md": _readme(name, business_type, primary_goal),
        "AGENTS.md": _agents(name),
        "scripts/validate_generated_project.sh": _validation_script(),
        "specs/001-product-foundation/spec.md": _initial_spec(
            name,
            business_type,
            primary_goal,
            workflow,
        ),
        "specs/001-product-foundation/plan.md": _initial_plan(name),
        "specs/001-product-foundation/tasks.md": _initial_tasks(),
        "specs/001-product-foundation/metadata.yaml": _initial_metadata(slug, name),
        "docs/research/business-brief.md": _placeholder_doc(
            "Business Brief",
            "Codex research will summarize the business, users, and product risks here.",
        ),
        "docs/research/typical-apps.md": _placeholder_doc(
            "Typical Apps",
            "Codex research will document common app patterns for this business type here.",
        ),
        "docs/research/visual-reference-analysis.md": _placeholder_doc(
            "Visual Reference Analysis",
            "Uploaded visual references will be analyzed here.",
        ),
        "docs/research/feature-map.md": _placeholder_doc(
            "Feature Map",
            "Domain features and suggested MVP scope will be tracked here.",
        ),
        "design/app-style-guide.md": _placeholder_doc(
            "App Style Guide",
            "Generated look and feel decisions will be documented here.",
        ),
        "design/tokens.yaml": _to_yaml(
            {
                "schema_version": 1,
                "source": "project-factory-placeholder",
                "colors": {},
                "typography": {},
                "spacing": {},
            }
        ),
        "infra/aws/recommended-architecture.md": _placeholder_doc(
            "AWS Recommended Architecture",
            "AWS deployment recommendations will be generated here.",
        ),
        "infra/aws/iam-required-permissions.md": _placeholder_doc(
            "IAM Required Permissions",
            "Least-privilege IAM requirements will be generated here.",
        ),
        "infra/aws/deploy-plan.md": _placeholder_doc(
            "Deploy Plan",
            "The deployment plan will be generated here.",
        ),
        "release/app-store-checklist.md": _placeholder_doc(
            "App Store Checklist",
            "Apple release readiness items and pending credentials will be tracked here.",
        ),
        "release/play-store-checklist.md": _placeholder_doc(
            "Play Store Checklist",
            "Google Play release readiness items and pending credentials will be tracked here.",
        ),
    }
    files.update(_backend_files(slug))
    files.update(_mobile_files(name, slug))
    return files


def _readme(name: str, business_type: str, primary_goal: str) -> str:
    return f"""# {name}

Generated by Codex Mobile Bridge Project Factory.

## Product

- Business type: `{business_type}`
- Primary goal: {primary_goal}
- Data mode: real by default

## Structure

- `.codex/project.yaml`: source of truth for project generation and validation.
- `specs/001-product-foundation/`: initial SDD package for Workbench-driven work.
- `apps/mobile/`: Flutter app target.
- `backend/`: API target.
- `docs/research/`: business, UX, and visual research.
- `design/`: visual direction and design tokens.
- `infra/aws/`: AWS readiness.
- `release/`: App Store and Play Store readiness.

## Validation

Run the generated backend and mobile contract validation with:

```bash
scripts/validate_generated_project.sh
```

The script uses process-local validation credentials unless `DATABASE_URL`,
`SECRET_KEY`, `ADMIN_EMAIL`, and `ADMIN_INITIAL_PASSWORD` are already set. It
does not write secrets to repository files.
"""


def _backend_files(slug: str) -> dict[str, str]:
    return {
        "backend/pyproject.toml": _backend_pyproject(slug),
        "backend/.env.example": _backend_env_example(),
        "backend/README.md": _backend_readme(),
        "backend/app/__init__.py": "",
        "backend/app/config.py": _backend_config_py(),
        "backend/app/db.py": _backend_db_py(),
        "backend/app/security.py": _backend_security_py(),
        "backend/app/main.py": _backend_main_py(),
        "backend/app/routers/__init__.py": "",
        "backend/app/routers/auth.py": _backend_auth_router_py(),
        "backend/app/routers/admin.py": _backend_admin_router_py(),
        "backend/app/routers/notifications.py": _backend_notifications_router_py(),
        "backend/app/routers/google.py": _backend_google_router_py(),
        "backend/tests/test_backend.py": _backend_tests_py(),
    }


def _validation_script() -> str:
    return r'''#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
MOBILE_DIR="$ROOT_DIR/apps/mobile"
VALIDATION_DIR="$ROOT_DIR/.generated-validation"
PYTHON_BIN="${PYTHON_BIN:-python3}"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-0}"
BACKEND_HEALTH_TIMEOUT_SECONDS="${BACKEND_HEALTH_TIMEOUT_SECONDS:-30}"
VALIDATION_VENV="${VALIDATION_VENV:-$BACKEND_DIR/.venv}"

mkdir -p "$VALIDATION_DIR"

random_secret() {
  "$PYTHON_BIN" - <<'PY'
import secrets
print(secrets.token_urlsafe(32))
PY
}

free_port() {
  "$PYTHON_BIN" - <<'PY'
import socket
sock = socket.socket()
sock.bind(("127.0.0.1", 0))
print(sock.getsockname()[1])
sock.close()
PY
}

if [ "$BACKEND_PORT" = "0" ]; then
  BACKEND_PORT="$(free_port)"
fi

export BACKEND_HOST
export BACKEND_PORT
export BACKEND_HEALTH_TIMEOUT_SECONDS

if [ -z "${DATABASE_URL:-}" ]; then
  rm -f "$VALIDATION_DIR/app.db"
  export DATABASE_URL="sqlite:///$VALIDATION_DIR/app.db"
else
  export DATABASE_URL
fi
export SECRET_KEY="${SECRET_KEY:-$(random_secret)}"
export ADMIN_EMAIL="${ADMIN_EMAIL:-admin.validation@example.com}"
export ADMIN_INITIAL_PASSWORD="${ADMIN_INITIAL_PASSWORD:-$(random_secret)}"
export CORS_ORIGINS="${CORS_ORIGINS:-http://127.0.0.1:$BACKEND_PORT}"

if [ ! -x "$VALIDATION_VENV/bin/python" ]; then
  "$PYTHON_BIN" -m venv "$VALIDATION_VENV"
fi

# shellcheck disable=SC1091
. "$VALIDATION_VENV/bin/activate"

cd "$BACKEND_DIR"
python -m pip install -e ".[dev]"
python -m pytest

python -m uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" > "$VALIDATION_DIR/backend.log" 2>&1 &
BACKEND_PID="$!"

cleanup() {
  if kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
    wait "$BACKEND_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

python - <<'PY'
import os
import time
import urllib.request

url = f"http://{os.environ.get('BACKEND_HOST', '127.0.0.1')}:{os.environ['BACKEND_PORT']}/health"
deadline = time.time() + int(os.environ.get("BACKEND_HEALTH_TIMEOUT_SECONDS", "30"))
last_error = None
while time.time() < deadline:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            if response.status == 200:
                print(f"backend health ok: {url}")
                raise SystemExit(0)
    except Exception as exc:
        last_error = exc
        time.sleep(0.5)
raise SystemExit(f"backend health timeout for {url}: {last_error}")
PY

python - <<'PY'
import json
import os
import urllib.error
import urllib.request

base_url = f"http://{os.environ.get('BACKEND_HOST', '127.0.0.1')}:{os.environ['BACKEND_PORT']}"

def request(method, path, payload=None, token=None):
    data = None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        data = json.dumps(payload).encode()
    req = urllib.request.Request(base_url + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            body = response.read().decode()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        raise AssertionError(f"{method} {path} failed: {exc.code} {body}") from exc

login = request(
    "POST",
    "/auth/login",
    {
        "email": os.environ["ADMIN_EMAIL"],
        "password": os.environ["ADMIN_INITIAL_PASSWORD"],
    },
)
token = login["access_token"]
me = request("GET", "/auth/me", token=token)
assert "owner" in me["roles"], me
roles = request("GET", "/admin/roles", token=token)
assert "owner" in roles and "customer" in roles, roles
domains = request("GET", "/admin/domains", token=token)
assert isinstance(domains, list), domains
domain_name = "validation-domain-" + token[:8].lower().replace("_", "x").replace("-", "x")
created = request("POST", "/admin/domains", {"name": domain_name}, token=token)
assert created["name"] == domain_name, created
notifications = request("GET", "/notifications", token=token)
assert isinstance(notifications, list), notifications
print("contract ok: auth/me/admin/domains/notifications")
PY

if command -v flutter >/dev/null 2>&1; then
  cd "$MOBILE_DIR"
  flutter test --dart-define=API_BASE_URL="http://$BACKEND_HOST:$BACKEND_PORT"
else
  echo "flutter not found; skipping mobile template tests"
fi

echo "generated project validation completed"
'''


def _mobile_files(name: str, slug: str) -> dict[str, str]:
    package_name = _dart_package_name(slug)
    return {
        "apps/mobile/pubspec.yaml": _mobile_pubspec(package_name),
        "apps/mobile/README.md": _mobile_readme(name),
        "apps/mobile/lib/main.dart": _mobile_main_dart(name),
        "apps/mobile/lib/src/config.dart": _mobile_config_dart(),
        "apps/mobile/lib/src/models.dart": _mobile_models_dart(),
        "apps/mobile/lib/src/api_client.dart": _mobile_api_client_dart(),
        "apps/mobile/lib/src/session_controller.dart": _mobile_session_controller_dart(),
        "apps/mobile/lib/src/screens.dart": _mobile_screens_dart(name),
        "apps/mobile/test/config_test.dart": _mobile_config_test_dart(package_name),
        "apps/mobile/test/api_client_test.dart": _mobile_api_client_test_dart(
            package_name
        ),
        "apps/mobile/test/session_controller_test.dart": (
            _mobile_session_controller_test_dart(package_name)
        ),
    }


def _dart_package_name(slug: str) -> str:
    package_name = slug.replace("-", "_")
    if package_name[0].isdigit():
        return f"app_{package_name}"
    return package_name


def _mobile_pubspec(package_name: str) -> str:
    return f"""name: {package_name}
description: Flutter app generated by Codex Mobile Bridge Project Factory.
publish_to: "none"
version: 0.1.0+1

environment:
  sdk: ">=3.4.0 <4.0.0"

dependencies:
  flutter:
    sdk: flutter
  http: ^1.2.2

dev_dependencies:
  flutter_test:
    sdk: flutter

flutter:
  uses-material-design: true
"""


def _mobile_readme(name: str) -> str:
    return f"""# {name} Mobile

Flutter app generated by Project Factory. It uses real backend calls and does
not include mock/demo runtime data.

## Run

Start the generated backend first, then run:

```bash
flutter pub get
flutter run --dart-define=API_BASE_URL=http://localhost:8000
```

For Android emulator talking to a backend on the host machine:

```bash
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

## Tests

```bash
flutter test
```

Session tokens are kept in memory in template v1. Add secure storage in a later
slice when persistence across app restarts is required.
"""


def _mobile_main_dart(name: str) -> str:
    return f"""import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import 'src/api_client.dart';
import 'src/config.dart';
import 'src/screens.dart';
import 'src/session_controller.dart';

void main() {{
  const apiBaseUrl = String.fromEnvironment('API_BASE_URL');
  final config = AppConfig.fromApiBaseUrl(apiBaseUrl);
  runApp(ProjectApp(config: config));
}}

class ProjectApp extends StatelessWidget {{
  const ProjectApp({{super.key, required this.config}});

  final AppConfig config;

  @override
  Widget build(BuildContext context) {{
    if (!config.isConfigured) {{
      return MaterialApp(
        title: '{name}',
        home: ConfigMissingScreen(message: config.errorMessage),
      );
    }}
    final api = ProjectApiClient(
      baseUrl: config.apiBaseUrl!,
      client: http.Client(),
    );
    return MaterialApp(
      title: '{name}',
      theme: ThemeData(useMaterial3: true, colorSchemeSeed: Colors.teal),
      home: ProjectHome(
        projectName: '{name}',
        controller: SessionController(api: api),
      ),
    );
  }}
}}
"""


def _mobile_config_dart() -> str:
    return """class AppConfig {
  const AppConfig({required this.apiBaseUrl});

  final String? apiBaseUrl;

  bool get isConfigured => apiBaseUrl != null && apiBaseUrl!.isNotEmpty;

  String get errorMessage {
    return 'API_BASE_URL is required. Run with --dart-define=API_BASE_URL=http://host:port';
  }

  factory AppConfig.fromApiBaseUrl(String value) {
    final trimmed = value.trim().replaceAll(RegExp(r'/$'), '');
    return AppConfig(apiBaseUrl: trimmed.isEmpty ? null : trimmed);
  }
}
"""


def _mobile_models_dart() -> str:
    return """class AppUser {
  const AppUser({required this.id, required this.email, required this.roles});

  final int id;
  final String email;
  final List<String> roles;

  bool get canAccessAdmin => roles.contains('owner') || roles.contains('admin');

  factory AppUser.fromJson(Map<String, dynamic> json) {
    return AppUser(
      id: json['id'] as int,
      email: json['email'] as String,
      roles: (json['roles'] as List<dynamic>? ?? <dynamic>[])
          .whereType<String>()
          .toList(growable: false),
    );
  }
}

class AuthToken {
  const AuthToken({required this.accessToken, required this.tokenType});

  final String accessToken;
  final String tokenType;

  factory AuthToken.fromJson(Map<String, dynamic> json) {
    return AuthToken(
      accessToken: json['access_token'] as String,
      tokenType: json['token_type'] as String? ?? 'bearer',
    );
  }
}

class AdminUser {
  const AdminUser({required this.id, required this.email, required this.isActive});
  final int id;
  final String email;
  final bool isActive;

  factory AdminUser.fromJson(Map<String, dynamic> json) {
    return AdminUser(
      id: json['id'] as int,
      email: json['email'] as String,
      isActive: json['is_active'] as bool,
    );
  }
}

class DomainRecord {
  const DomainRecord({required this.id, required this.name, required this.isActive});
  final int id;
  final String name;
  final bool isActive;

  factory DomainRecord.fromJson(Map<String, dynamic> json) {
    return DomainRecord(
      id: json['id'] as int,
      name: json['name'] as String,
      isActive: json['is_active'] as bool,
    );
  }
}

class AppNotification {
  const AppNotification({
    required this.id,
    required this.title,
    required this.body,
    required this.readAt,
    required this.createdAt,
  });

  final int id;
  final String title;
  final String body;
  final String? readAt;
  final String createdAt;

  bool get isRead => readAt != null;

  factory AppNotification.fromJson(Map<String, dynamic> json) {
    return AppNotification(
      id: json['id'] as int,
      title: json['title'] as String,
      body: json['body'] as String,
      readAt: json['read_at'] as String?,
      createdAt: json['created_at'] as String,
    );
  }
}
"""


def _mobile_api_client_dart() -> str:
    return """import 'dart:convert';

import 'package:http/http.dart' as http;

import 'models.dart';

class ProjectApiClient {
  ProjectApiClient({required this.baseUrl, http.Client? client})
      : _client = client ?? http.Client();

  final String baseUrl;
  final http.Client _client;

  Future<bool> health() async {
    final response = await _client.get(Uri.parse('$baseUrl/health'));
    return response.statusCode == 200;
  }

  Future<AuthToken> register({required String email, required String password}) async {
    final response = await _postJson('/auth/register', {'email': email, 'password': password});
    if (response.statusCode != 200) {
      throw ApiException('Register failed', response.statusCode, response.body);
    }
    return login(email: email, password: password);
  }

  Future<AuthToken> login({required String email, required String password}) async {
    final response = await _postJson('/auth/login', {'email': email, 'password': password});
    if (response.statusCode != 200) {
      throw ApiException('Login failed', response.statusCode, response.body);
    }
    return AuthToken.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }

  Future<AppUser> me(String token) async {
    final response = await _client.get(_uri('/auth/me'), headers: _authHeaders(token));
    if (response.statusCode != 200) {
      throw ApiException('Me failed', response.statusCode, response.body);
    }
    return AppUser.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }

  Future<void> logout(String token) async {
    await _client.post(_uri('/auth/logout'), headers: _authHeaders(token));
  }

  Future<List<AdminUser>> adminUsers(String token) async {
    final response = await _client.get(_uri('/admin/users'), headers: _authHeaders(token));
    if (response.statusCode != 200) {
      throw ApiException('Admin users failed', response.statusCode, response.body);
    }
    return _list(response).map(AdminUser.fromJson).toList(growable: false);
  }

  Future<List<String>> adminRoles(String token) async {
    final response = await _client.get(_uri('/admin/roles'), headers: _authHeaders(token));
    if (response.statusCode != 200) {
      throw ApiException('Admin roles failed', response.statusCode, response.body);
    }
    return (jsonDecode(response.body) as List<dynamic>).whereType<String>().toList();
  }

  Future<List<DomainRecord>> domains(String token) async {
    final response = await _client.get(_uri('/admin/domains'), headers: _authHeaders(token));
    if (response.statusCode != 200) {
      throw ApiException('Domains failed', response.statusCode, response.body);
    }
    return _list(response).map(DomainRecord.fromJson).toList(growable: false);
  }

  Future<DomainRecord> createDomain(String token, String name) async {
    final response = await _postJson('/admin/domains', {'name': name}, token: token);
    if (response.statusCode != 200) {
      throw ApiException('Create domain failed', response.statusCode, response.body);
    }
    return DomainRecord.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }

  Future<List<AppNotification>> notifications(String token) async {
    final response = await _client.get(_uri('/notifications'), headers: _authHeaders(token));
    if (response.statusCode != 200) {
      throw ApiException('Notifications failed', response.statusCode, response.body);
    }
    return _list(response).map(AppNotification.fromJson).toList(growable: false);
  }

  Future<void> markNotificationRead(String token, int id) async {
    final response = await _client.post(_uri('/notifications/$id/read'), headers: _authHeaders(token));
    if (response.statusCode != 200) {
      throw ApiException('Mark notification read failed', response.statusCode, response.body);
    }
  }

  Future<http.Response> _postJson(String path, Map<String, Object?> body, {String? token}) {
    return _client.post(
      _uri(path),
      headers: <String, String>{
        'Content-Type': 'application/json',
        if (token != null) ..._authHeaders(token),
      },
      body: jsonEncode(body),
    );
  }

  Uri _uri(String path) => Uri.parse('$baseUrl$path');

  Map<String, String> _authHeaders(String token) {
    return {'Authorization': 'Bearer $token'};
  }

  List<Map<String, dynamic>> _list(http.Response response) {
    return (jsonDecode(response.body) as List<dynamic>)
        .cast<Map<String, dynamic>>();
  }
}

class ApiException implements Exception {
  ApiException(this.message, this.statusCode, this.body);
  final String message;
  final int statusCode;
  final String body;

  @override
  String toString() => '$message ($statusCode): $body';
}
"""


def _mobile_session_controller_dart() -> str:
    return """import 'package:flutter/foundation.dart';

import 'api_client.dart';
import 'models.dart';

class SessionController extends ChangeNotifier {
  SessionController({required this.api});

  final ProjectApiClient api;
  String? token;
  AppUser? user;
  bool loading = false;
  String? error;

  bool get isAuthenticated => token != null && user != null;

  Future<void> login({required String email, required String password}) async {
    await _run(() async {
      final auth = await api.login(email: email, password: password);
      token = auth.accessToken;
      user = await api.me(token!);
    });
  }

  Future<void> register({required String email, required String password}) async {
    await _run(() async {
      final auth = await api.register(email: email, password: password);
      token = auth.accessToken;
      user = await api.me(token!);
    });
  }

  Future<void> logout() async {
    final currentToken = token;
    token = null;
    user = null;
    notifyListeners();
    if (currentToken != null) {
      await api.logout(currentToken);
    }
  }

  Future<void> _run(Future<void> Function() action) async {
    loading = true;
    error = null;
    notifyListeners();
    try {
      await action();
    } catch (err) {
      error = err.toString();
    } finally {
      loading = false;
      notifyListeners();
    }
  }
}
"""


def _mobile_screens_dart(name: str) -> str:
    return f"""import 'package:flutter/material.dart';

import 'api_client.dart';
import 'models.dart';
import 'session_controller.dart';

class ConfigMissingScreen extends StatelessWidget {{
  const ConfigMissingScreen({{super.key, required this.message}});
  final String message;

  @override
  Widget build(BuildContext context) {{
    return Scaffold(
      appBar: AppBar(title: const Text('{name}')),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Text(message, textAlign: TextAlign.center),
        ),
      ),
    );
  }}
}}

class ProjectHome extends StatefulWidget {{
  const ProjectHome({{
    super.key,
    required this.projectName,
    required this.controller,
  }});

  final String projectName;
  final SessionController controller;

  @override
  State<ProjectHome> createState() => _ProjectHomeState();
}}

class _ProjectHomeState extends State<ProjectHome> {{
  int _index = 0;

  @override
  Widget build(BuildContext context) {{
    return AnimatedBuilder(
      animation: widget.controller,
      builder: (context, _) {{
        if (!widget.controller.isAuthenticated) {{
          return AuthScreen(controller: widget.controller, projectName: widget.projectName);
        }}
        final user = widget.controller.user!;
        final pages = <Widget>[
          HomeScreen(user: user, onLogout: widget.controller.logout),
          NotificationsScreen(api: widget.controller.api, token: widget.controller.token!),
          if (user.canAccessAdmin)
            AdminScreen(api: widget.controller.api, token: widget.controller.token!),
        ];
        return Scaffold(
          appBar: AppBar(title: Text(widget.projectName)),
          body: pages[_index.clamp(0, pages.length - 1)],
          bottomNavigationBar: NavigationBar(
            selectedIndex: _index.clamp(0, pages.length - 1),
            onDestinationSelected: (value) => setState(() => _index = value),
            destinations: <Widget>[
              const NavigationDestination(icon: Icon(Icons.home_outlined), label: 'Home'),
              const NavigationDestination(icon: Icon(Icons.notifications_outlined), label: 'Notifications'),
              if (user.canAccessAdmin)
                const NavigationDestination(icon: Icon(Icons.admin_panel_settings_outlined), label: 'Admin'),
            ],
          ),
        );
      }},
    );
  }}
}}

class AuthScreen extends StatefulWidget {{
  const AuthScreen({{super.key, required this.controller, required this.projectName}});
  final SessionController controller;
  final String projectName;

  @override
  State<AuthScreen> createState() => _AuthScreenState();
}}

class _AuthScreenState extends State<AuthScreen> {{
  final _email = TextEditingController();
  final _password = TextEditingController();
  bool _register = false;

  @override
  void dispose() {{
    _email.dispose();
    _password.dispose();
    super.dispose();
  }}

  @override
  Widget build(BuildContext context) {{
    return Scaffold(
      appBar: AppBar(title: Text(widget.projectName)),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 420),
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                TextField(controller: _email, decoration: const InputDecoration(labelText: 'Email')),
                const SizedBox(height: 12),
                TextField(controller: _password, decoration: const InputDecoration(labelText: 'Password'), obscureText: true),
                const SizedBox(height: 16),
                if (widget.controller.error != null)
                  Text(widget.controller.error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
                const SizedBox(height: 8),
                FilledButton(
                  onPressed: widget.controller.loading ? null : _submit,
                  child: Text(_register ? 'Register' : 'Login'),
                ),
                TextButton(
                  onPressed: () => setState(() => _register = !_register),
                  child: Text(_register ? 'Use login' : 'Create account'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }}

  Future<void> _submit() async {{
    if (_register) {{
      await widget.controller.register(email: _email.text.trim(), password: _password.text);
    }} else {{
      await widget.controller.login(email: _email.text.trim(), password: _password.text);
    }}
  }}
}}

class HomeScreen extends StatelessWidget {{
  const HomeScreen({{super.key, required this.user, required this.onLogout}});
  final AppUser user;
  final Future<void> Function() onLogout;

  @override
  Widget build(BuildContext context) {{
    return ListView(
      padding: const EdgeInsets.all(20),
      children: <Widget>[
        Text(user.email, style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 8),
        Text('Roles: ${{user.roles.join(', ')}}'),
        const SizedBox(height: 16),
        OutlinedButton(onPressed: onLogout, child: const Text('Logout')),
      ],
    );
  }}
}}

class AdminScreen extends StatefulWidget {{
  const AdminScreen({{super.key, required this.api, required this.token}});
  final ProjectApiClient api;
  final String token;

  @override
  State<AdminScreen> createState() => _AdminScreenState();
}}

class _AdminScreenState extends State<AdminScreen> {{
  late Future<void> _load;
  List<AdminUser> _users = <AdminUser>[];
  List<String> _roles = <String>[];
  List<DomainRecord> _domains = <DomainRecord>[];
  final _domain = TextEditingController();

  @override
  void initState() {{
    super.initState();
    _load = _refresh();
  }}

  @override
  void dispose() {{
    _domain.dispose();
    super.dispose();
  }}

  Future<void> _refresh() async {{
    _users = await widget.api.adminUsers(widget.token);
    _roles = await widget.api.adminRoles(widget.token);
    _domains = await widget.api.domains(widget.token);
  }}

  @override
  Widget build(BuildContext context) {{
    return FutureBuilder<void>(
      future: _load,
      builder: (context, snapshot) {{
        if (snapshot.connectionState != ConnectionState.done) {{
          return const Center(child: CircularProgressIndicator());
        }}
        if (snapshot.hasError) {{
          return Center(child: Text(snapshot.error.toString()));
        }}
        return ListView(
          padding: const EdgeInsets.all(20),
          children: <Widget>[
            Text('Users', style: Theme.of(context).textTheme.titleMedium),
            if (_users.isEmpty) const Text('No users'),
            ..._users.map((user) => ListTile(title: Text(user.email), subtitle: Text(user.isActive ? 'active' : 'inactive'))),
            const Divider(),
            Text('Roles: ${{_roles.join(', ')}}'),
            const Divider(),
            TextField(controller: _domain, decoration: const InputDecoration(labelText: 'New domain')),
            FilledButton(onPressed: _createDomain, child: const Text('Create domain')),
            if (_domains.isEmpty) const Text('No domains'),
            ..._domains.map((domain) => ListTile(title: Text(domain.name))),
          ],
        );
      }},
    );
  }}

  Future<void> _createDomain() async {{
    final name = _domain.text.trim();
    if (name.isEmpty) return;
    await widget.api.createDomain(widget.token, name);
    _domain.clear();
    setState(() => _load = _refresh());
  }}
}}

class NotificationsScreen extends StatefulWidget {{
  const NotificationsScreen({{super.key, required this.api, required this.token}});
  final ProjectApiClient api;
  final String token;

  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}}

class _NotificationsScreenState extends State<NotificationsScreen> {{
  late Future<List<AppNotification>> _load;

  @override
  void initState() {{
    super.initState();
    _load = widget.api.notifications(widget.token);
  }}

  @override
  Widget build(BuildContext context) {{
    return FutureBuilder<List<AppNotification>>(
      future: _load,
      builder: (context, snapshot) {{
        if (snapshot.connectionState != ConnectionState.done) {{
          return const Center(child: CircularProgressIndicator());
        }}
        if (snapshot.hasError) {{
          return Center(child: Text(snapshot.error.toString()));
        }}
        final items = snapshot.data ?? <AppNotification>[];
        if (items.isEmpty) {{
          return const Center(child: Text('No notifications'));
        }}
        return ListView(
          children: items.map((item) {{
            return ListTile(
              title: Text(item.title),
              subtitle: Text(item.body),
              trailing: item.isRead
                  ? const Icon(Icons.done)
                  : IconButton(
                      icon: const Icon(Icons.mark_email_read_outlined),
                      onPressed: () async {{
                        await widget.api.markNotificationRead(widget.token, item.id);
                        setState(() => _load = widget.api.notifications(widget.token));
                      }},
                    ),
            );
          }}).toList(),
        );
      }},
    );
  }}
}}
"""


def _mobile_config_test_dart(package_name: str) -> str:
    return f"""import 'package:flutter_test/flutter_test.dart';
import 'package:{package_name}/src/config.dart';

void main() {{
  test('config requires API_BASE_URL', () {{
    expect(AppConfig.fromApiBaseUrl('').isConfigured, isFalse);
    expect(AppConfig.fromApiBaseUrl('http://localhost:8000/').apiBaseUrl, 'http://localhost:8000');
  }});
}}
"""


def _mobile_api_client_test_dart(package_name: str) -> str:
    return f"""import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:{package_name}/src/api_client.dart';

void main() {{
  test('api client calls auth admin and notifications endpoints', () async {{
    final calls = <String>[];
    final api = ProjectApiClient(
      baseUrl: 'http://api.test',
      client: MockClient((request) async {{
        calls.add('${{request.method}} ${{request.url.path}}');
        if (request.url.path == '/health') return http.Response('{{"status":"ok"}}', 200);
        if (request.url.path == '/auth/login') return http.Response('{{"access_token":"t","token_type":"bearer"}}', 200);
        if (request.url.path == '/auth/me') return http.Response('{{"id":1,"email":"a@example.com","roles":["owner"]}}', 200);
        if (request.url.path == '/admin/users') return http.Response('[{{"id":1,"email":"a@example.com","is_active":true}}]', 200);
        if (request.url.path == '/admin/roles') return http.Response('["owner","customer"]', 200);
        if (request.url.path == '/admin/domains' && request.method == 'GET') return http.Response('[{{"id":1,"name":"primary","is_active":true}}]', 200);
        if (request.url.path == '/admin/domains' && request.method == 'POST') return http.Response('{{"id":2,"name":"new","is_active":true}}', 200);
        if (request.url.path == '/notifications' && request.method == 'GET') return http.Response('[{{"id":1,"title":"Welcome","body":"Hi","read_at":null,"created_at":"now"}}]', 200);
        if (request.url.path == '/notifications/1/read') return http.Response('{{"status":"read"}}', 200);
        return http.Response('missing', 404);
      }}),
    );
    expect(await api.health(), isTrue);
    final token = await api.login(email: 'a@example.com', password: 'secret');
    expect(token.accessToken, 't');
    expect((await api.me('t')).canAccessAdmin, isTrue);
    expect(await api.adminUsers('t'), hasLength(1));
    expect(await api.adminRoles('t'), contains('owner'));
    expect(await api.domains('t'), hasLength(1));
    expect((await api.createDomain('t', 'new')).name, 'new');
    expect(await api.notifications('t'), hasLength(1));
    await api.markNotificationRead('t', 1);
    expect(calls, contains('GET /health'));
  }});
}}
"""


def _mobile_session_controller_test_dart(package_name: str) -> str:
    return f"""import 'package:flutter_test/flutter_test.dart';
import 'package:{package_name}/src/api_client.dart';
import 'package:{package_name}/src/models.dart';
import 'package:{package_name}/src/session_controller.dart';

void main() {{
  test('session login stores token and user', () async {{
    final controller = SessionController(api: _FakeApi());
    await controller.login(email: 'admin@example.com', password: 'secret');
    expect(controller.isAuthenticated, isTrue);
    expect(controller.user!.canAccessAdmin, isTrue);
  }});

  test('rbac denies admin for customer role', () {{
    const user = AppUser(id: 1, email: 'user@example.com', roles: ['customer']);
    expect(user.canAccessAdmin, isFalse);
  }});
}}

class _FakeApi extends ProjectApiClient {{
  _FakeApi() : super(baseUrl: 'http://fake');

  @override
  Future<AuthToken> login({{required String email, required String password}}) async {{
    return const AuthToken(accessToken: 'token', tokenType: 'bearer');
  }}

  @override
  Future<AppUser> me(String token) async {{
    return const AppUser(id: 1, email: 'admin@example.com', roles: ['owner']);
  }}
}}
"""


def _backend_pyproject(slug: str) -> str:
    return f"""[build-system]
requires = ["setuptools>=69", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "{slug}-backend"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115,<1.0",
    "uvicorn[standard]>=0.35,<1.0",
    "python-dotenv>=1.0,<2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3,<9.0",
    "httpx>=0.28,<1.0",
]
"""


def _backend_env_example() -> str:
    return """DATABASE_URL=sqlite:///./app.db
SECRET_KEY=
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
ADMIN_EMAIL=
ADMIN_INITIAL_PASSWORD=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
"""


def _backend_readme() -> str:
    return """# Backend

FastAPI backend generated by Project Factory.

## Setup

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Set real values in `.env`:

- `DATABASE_URL`
- `SECRET_KEY`
- `ADMIN_EMAIL`
- `ADMIN_INITIAL_PASSWORD`

If `ADMIN_EMAIL` or `ADMIN_INITIAL_PASSWORD` are missing, no admin is seeded.
Google auth is prepared but returns a clear pending-credentials error until
Google credentials are configured.

## Run

```bash
uvicorn app.main:app --reload
```

## Test

```bash
pytest
```
"""


def _backend_config_py() -> str:
    return '''from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    secret_key: str | None
    cors_origins: tuple[str, ...]
    admin_email: str | None
    admin_initial_password: str | None
    google_client_id: str | None
    google_client_secret: str | None


def get_settings() -> Settings:
    origins = tuple(
        item.strip()
        for item in os.getenv("CORS_ORIGINS", "*").split(",")
        if item.strip()
    )
    return Settings(
        database_url=os.getenv("DATABASE_URL", "sqlite:///./app.db"),
        secret_key=os.getenv("SECRET_KEY") or None,
        cors_origins=origins or ("*",),
        admin_email=os.getenv("ADMIN_EMAIL") or None,
        admin_initial_password=os.getenv("ADMIN_INITIAL_PASSWORD") or None,
        google_client_id=os.getenv("GOOGLE_CLIENT_ID") or None,
        google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET") or None,
    )
'''


def _backend_db_py() -> str:
    return '''from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .config import get_settings

ROLES = ("owner", "admin", "manager", "staff", "customer", "guest")


def database_path() -> Path:
    url = get_settings().database_url
    if not url.startswith("sqlite:///"):
        raise RuntimeError("Only sqlite:/// DATABASE_URL is supported by backend v1.")
    return Path(url.removeprefix("sqlite:///")).expanduser()


@contextmanager
def connect():
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS roles (
                name TEXT PRIMARY KEY
            );
            CREATE TABLE IF NOT EXISTS user_roles (
                user_id INTEGER NOT NULL,
                role_name TEXT NOT NULL,
                UNIQUE(user_id, role_name)
            );
            CREATE TABLE IF NOT EXISTS domains (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                read_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        for role in ROLES:
            conn.execute("INSERT OR IGNORE INTO roles(name) VALUES (?)", (role,))
    seed_admin()


def seed_admin() -> None:
    from .security import hash_password

    settings = get_settings()
    if not settings.admin_email or not settings.admin_initial_password:
        return
    with connect() as conn:
        existing = conn.execute(
            "SELECT id FROM users WHERE email = ?",
            (settings.admin_email,),
        ).fetchone()
        if existing is None:
            cursor = conn.execute(
                "INSERT INTO users(email, password_hash, is_active) VALUES (?, ?, 1)",
                (settings.admin_email, hash_password(settings.admin_initial_password)),
            )
            user_id = int(cursor.lastrowid)
        else:
            user_id = int(existing["id"])
        conn.execute(
            "INSERT OR IGNORE INTO user_roles(user_id, role_name) VALUES (?, ?)",
            (user_id, "owner"),
        )
'''


def _backend_security_py() -> str:
    return '''from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

from fastapi import Depends, Header, HTTPException

from .config import get_settings
from .db import connect


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 210_000)
    return "pbkdf2_sha256$" + base64.urlsafe_b64encode(salt).decode() + "$" + base64.urlsafe_b64encode(digest).decode()


def verify_password(password: str, encoded: str) -> bool:
    try:
        _scheme, salt_b64, digest_b64 = encoded.split("$", 2)
        salt = base64.urlsafe_b64decode(salt_b64.encode())
        expected = base64.urlsafe_b64decode(digest_b64.encode())
    except Exception:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 210_000)
    return hmac.compare_digest(actual, expected)


def create_token(user_id: int) -> str:
    secret = get_settings().secret_key
    if not secret:
        raise HTTPException(status_code=500, detail="SECRET_KEY is required for auth.")
    header = _b64({"alg": "HS256", "typ": "JWT"})
    payload = _b64({"sub": str(user_id), "iat": int(time.time())})
    signature = _sign(f"{header}.{payload}", secret)
    return f"{header}.{payload}.{signature}"


def decode_token(token: str) -> int:
    secret = get_settings().secret_key
    if not secret:
        raise HTTPException(status_code=500, detail="SECRET_KEY is required for auth.")
    try:
        header, payload, signature = token.split(".", 2)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid token.") from None
    if not hmac.compare_digest(_sign(f"{header}.{payload}", secret), signature):
        raise HTTPException(status_code=401, detail="Invalid token.")
    data = json.loads(_unb64(payload))
    return int(data["sub"])


def current_user(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required.")
    user_id = decode_token(authorization.split(" ", 1)[1])
    with connect() as conn:
        user = conn.execute(
            "SELECT id, email, is_active FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if user is None or not int(user["is_active"]):
            raise HTTPException(status_code=401, detail="Inactive or missing user.")
        roles = conn.execute(
            "SELECT role_name FROM user_roles WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    return {
        "id": int(user["id"]),
        "email": str(user["email"]),
        "roles": [str(row["role_name"]) for row in roles],
    }


def require_roles(*allowed_roles: str):
    def dependency(user=Depends(current_user)):
        if "owner" in user["roles"] or any(role in user["roles"] for role in allowed_roles):
            return user
        raise HTTPException(status_code=403, detail="Insufficient role.")

    return dependency


def _b64(data: dict[str, object]) -> str:
    raw = json.dumps(data, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(data: str) -> str:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode()).decode()


def _sign(data: str, secret: str) -> str:
    digest = hmac.new(secret.encode(), data.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")
'''


def _backend_main_py() -> str:
    return '''from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import init_db
from .routers import admin, auth, google, notifications


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db()
        yield

    settings = get_settings()
    app = FastAPI(title="Generated Project Backend", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth.router)
    app.include_router(google.router)
    app.include_router(admin.router)
    app.include_router(notifications.router)
    return app


app = create_app()
'''


def _backend_auth_router_py() -> str:
    return '''from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..db import connect
from ..security import create_token, current_user, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class Credentials(BaseModel):
    email: str
    password: str


@router.post("/register")
def register(credentials: Credentials):
    with connect() as conn:
        try:
            cursor = conn.execute(
                "INSERT INTO users(email, password_hash, is_active) VALUES (?, ?, 1)",
                (credentials.email, hash_password(credentials.password)),
            )
        except Exception as exc:
            raise HTTPException(status_code=409, detail="User already exists.") from exc
        user_id = int(cursor.lastrowid)
        conn.execute(
            "INSERT OR IGNORE INTO user_roles(user_id, role_name) VALUES (?, ?)",
            (user_id, "customer"),
        )
    return {"id": user_id, "email": credentials.email}


@router.post("/login")
def login(credentials: Credentials):
    with connect() as conn:
        user = conn.execute(
            "SELECT id, email, password_hash, is_active FROM users WHERE email = ?",
            (credentials.email,),
        ).fetchone()
    if user is None or not int(user["is_active"]):
        raise HTTPException(status_code=401, detail="Invalid credentials.")
    if not verify_password(credentials.password, str(user["password_hash"])):
        raise HTTPException(status_code=401, detail="Invalid credentials.")
    return {"access_token": create_token(int(user["id"])), "token_type": "bearer"}


@router.get("/me")
def me(user=Depends(current_user)):
    return user


@router.post("/logout")
def logout():
    return {"status": "ok"}
'''


def _backend_admin_router_py() -> str:
    return '''from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..db import connect
from ..security import require_roles

router = APIRouter(prefix="/admin", tags=["admin"])


class DomainCreate(BaseModel):
    name: str


@router.get("/users")
def list_users(_user=Depends(require_roles("admin"))):
    with connect() as conn:
        rows = conn.execute("SELECT id, email, is_active FROM users ORDER BY id").fetchall()
    return [{"id": int(row["id"]), "email": row["email"], "is_active": bool(row["is_active"])} for row in rows]


@router.get("/roles")
def list_roles(_user=Depends(require_roles("admin"))):
    with connect() as conn:
        rows = conn.execute("SELECT name FROM roles ORDER BY name").fetchall()
    return [row["name"] for row in rows]


@router.get("/domains")
def list_domains(_user=Depends(require_roles("admin", "manager"))):
    with connect() as conn:
        rows = conn.execute("SELECT id, name, is_active FROM domains ORDER BY id").fetchall()
    return [{"id": int(row["id"]), "name": row["name"], "is_active": bool(row["is_active"])} for row in rows]


@router.post("/domains")
def create_domain(payload: DomainCreate, _user=Depends(require_roles("admin"))):
    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO domains(name, is_active) VALUES (?, 1)",
            (payload.name,),
        )
    return {"id": int(cursor.lastrowid), "name": payload.name, "is_active": True}
'''


def _backend_notifications_router_py() -> str:
    return '''from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..db import connect
from ..security import current_user

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
def list_notifications(user=Depends(current_user)):
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, title, body, read_at, created_at FROM notifications WHERE user_id = ? ORDER BY id DESC",
            (user["id"],),
        ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "title": row["title"],
            "body": row["body"],
            "read_at": row["read_at"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


@router.post("/{notification_id}/read")
def mark_read(notification_id: int, user=Depends(current_user)):
    with connect() as conn:
        row = conn.execute(
            "SELECT id FROM notifications WHERE id = ? AND user_id = ?",
            (notification_id, user["id"]),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Notification not found.")
        conn.execute(
            "UPDATE notifications SET read_at = CURRENT_TIMESTAMP WHERE id = ?",
            (notification_id,),
        )
    return {"status": "read", "id": notification_id}
'''


def _backend_google_router_py() -> str:
    return '''from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..config import get_settings

router = APIRouter(prefix="/auth/google", tags=["google-auth"])


@router.post("/login")
def google_login():
    settings = get_settings()
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(
            status_code=501,
            detail="Google auth credentials are pending. Configure GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.",
        )
    raise HTTPException(status_code=501, detail="Google auth exchange is not implemented in backend v1.")
'''


def _backend_tests_py() -> str:
    return '''from __future__ import annotations

from fastapi.testclient import TestClient

from app.db import connect
from app.main import create_app


def test_health_auth_rbac_and_notifications(monkeypatch, tmp_path):
    db_path = tmp_path / "app.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", "admin-password")

    with TestClient(create_app()) as client:
        assert client.get("/health").json() == {"status": "ok"}
        login = client.post(
            "/auth/login",
            json={"email": "admin@example.com", "password": "admin-password"},
        )
        assert login.status_code == 200
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        assert client.get("/auth/me", headers=headers).json()["roles"] == ["owner"]
        assert client.get("/admin/users", headers=headers).status_code == 200
        assert client.post(
            "/admin/domains",
            json={"name": "primary"},
            headers=headers,
        ).status_code == 200

        registered = client.post(
            "/auth/register",
            json={"email": "user@example.com", "password": "user-password"},
        )
        assert registered.status_code == 200
        user_login = client.post(
            "/auth/login",
            json={"email": "user@example.com", "password": "user-password"},
        )
        user_headers = {"Authorization": f"Bearer {user_login.json()['access_token']}"}
        assert client.get("/admin/users", headers=user_headers).status_code == 403

        with connect() as conn:
            conn.execute(
                "INSERT INTO notifications(user_id, title, body) VALUES (?, ?, ?)",
                (registered.json()["id"], "Welcome", "Hello"),
            )
        notifications = client.get("/notifications", headers=user_headers)
        assert notifications.status_code == 200
        notification_id = notifications.json()[0]["id"]
        assert client.post(
            f"/notifications/{notification_id}/read",
            headers=user_headers,
        ).status_code == 200


def test_google_auth_reports_pending_credentials(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'app.db'}")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    with TestClient(create_app()) as client:
        response = client.post("/auth/google/login")
    assert response.status_code == 501
    assert "pending" in response.json()["detail"].lower()
'''


def _agents(name: str) -> str:
    return f"""# Agent Notes For {name}

## Product Factory Defaults

This project was created by Codex Mobile Bridge Project Factory.

- Keep release builds on real data paths unless a demo/mock release is explicitly requested.
- Use Workbench specs, plans, and tasks as the primary feature planning surface.
- Keep secrets in environment variables or secret managers; do not commit them.
- The seed admin password must come from `SEED_ADMIN_PASSWORD`.
- Google login is required but may remain `pending_credentials` until real OAuth credentials are provided.
"""


def _initial_spec(
    name: str,
    business_type: str,
    primary_goal: str,
    workflow: dict[str, Any],
) -> str:
    return f"""# Product Foundation

## Intent

Build `{name}` as a Flutter iOS/Android/Web app with a FastAPI backend, auth,
admin, roles, permissions, domain management, notifications, Codex Feedback
Bridge, app updater, and Workbench-driven feature growth.

## Business Context

- Business type: `{business_type}`
- Primary goal: {primary_goal}

## Creation Workflow

New-project creation uses Codex CLI by default with:

- generator runs: {workflow["generator_runs"]}
- reviewer runs: {workflow["reviewer_runs"]}
- mode: `{workflow["mode"]}`

## Required Foundation

- Login and registration.
- Google login placeholders.
- RBAC with owner/admin/manager/staff/customer/guest.
- Admin domain-management shell.
- Notification foundations.
- FastAPI backend v1 with SQLite DATABASE_URL, PBKDF2 password hashing,
  JWT-compatible HS256 tokens, admin seed by env, RBAC guards, domain CRUD,
  notification outbox, healthcheck, CORS, and generated tests.
- Flutter mobile v1 with API_BASE_URL configuration, real auth/session calls,
  RBAC admin gating, domain management screens, notifications, and generated tests.
- SDD artifacts for future Workbench features.
"""


def _initial_plan(name: str) -> str:
    return f"""# Plan

Create the foundation for `{name}` in incremental validated slices:

1. Complete business research and visual direction.
2. Extend the generated Flutter auth/admin/notification app with domain UX.
3. Extend FastAPI backend v1 beyond the generated auth/RBAC/admin/notification base.
4. Add domain-specific resources and workflows.
5. Wire Feedback Bridge, updater, and Workbench.
6. Validate local run and release readiness.
"""


def _initial_tasks() -> str:
    return """# Tasks

- [ ] Complete business research.
- [ ] Complete visual reference analysis.
- [x] Generate Flutter mobile v1 with API_BASE_URL, auth/session, RBAC admin gating, domain management, notifications, and generated tests.
- [x] Generate backend v1 with FastAPI, auth, RBAC, admin, domain CRUD foundation, and notifications.
- [x] Add auth and Google login placeholders.
- [x] Add RBAC and admin shell.
- [x] Add domain CRUD foundation.
- [x] Add notification foundation.
- [ ] Wire Feedback Bridge and updater.
- [ ] Validate Workbench integration and release readiness.
"""


def _initial_metadata(slug: str, name: str) -> str:
    return _to_yaml(
        {
            "id": "001-product-foundation",
            "slug": "001-product-foundation",
            "title": "Product Foundation",
            "description": f"Initial product foundation for {name}.",
            "lifecycle_status": "draft",
            "created_at": None,
            "updated_at": None,
            "generated": {
                "title": False,
                "description": False,
                "user_pinned_title": True,
                "user_pinned_description": True,
            },
            "tasks": {"total": 10, "completed": 0, "pending": 10},
            "last_run_state": None,
            "metadata_status": "fresh",
            "metadata_warnings": [],
            "metadata_stale_paths": [],
            "available_files": ["spec.md", "plan.md", "tasks.md"],
            "diagrams": [],
            "project_slug": slug,
        }
    )


def _placeholder_doc(title: str, body: str) -> str:
    return f"# {title}\n\n{body}\n"


def _gitignore() -> str:
    return """.env
.env.*
!.env.example
.dart_tool/
build/
__pycache__/
*.pyc
.codex-bridge/
"""


def _init_git(target: Path) -> str:
    try:
        subprocess.run(
            ["git", "init"],
            cwd=target,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return "pending_git"
    return "initialized"


def _cleanup_created_target(target: Path) -> None:
    if not target.exists():
        return
    for child in sorted(target.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if child.is_file() or child.is_symlink():
            child.unlink(missing_ok=True)
        elif child.is_dir():
            child.rmdir()
    target.rmdir()


def _to_yaml(value: Any, *, indent: int = 0) -> str:
    text = _yaml_value(value, indent=indent)
    return text if text.endswith("\n") else text + "\n"


def _yaml_value(value: Any, *, indent: int) -> str:
    prefix = " " * indent
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}{key}:")
                lines.append(_yaml_value(item, indent=indent + 2).rstrip())
            else:
                lines.append(f"{prefix}{key}: {_yaml_scalar(item)}")
        return "\n".join(lines) + "\n"
    if isinstance(value, list):
        if not value:
            return f"{prefix}[]\n"
        lines = []
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}-")
                lines.append(_yaml_value(item, indent=indent + 2).rstrip())
            else:
                lines.append(f"{prefix}- {_yaml_scalar(item)}")
        return "\n".join(lines) + "\n"
    return f"{prefix}{_yaml_scalar(value)}\n"


def _yaml_scalar(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    if isinstance(value, int | float):
        return str(value)
    text = str(value)
    if not text:
        return '""'
    if re_match_plain_yaml(text):
        return text
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def re_match_plain_yaml(text: str) -> bool:
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-./")
    return all(char in allowed for char in text)
