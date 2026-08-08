from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from backend.app.application.services.project_scaffold_providers import (
    DeclarativeTargetProvider,
    ProviderBlocker,
    ProviderContext,
    ProviderDescriptor,
    ProviderResult,
    TargetPlan,
)
from backend.app.domain.entities.project_scaffold import (
    CapabilityEvidence,
    CapabilityEvidenceState,
    TargetKind,
)


@dataclass(frozen=True, slots=True)
class TemplateBundle:
    files: Mapping[str, str]
    bootstrap_commands: tuple[tuple[str, ...], ...] = ()
    validation_commands: tuple[tuple[str, ...], ...] = ()


class TemplateTargetProvider(DeclarativeTargetProvider):
    def __init__(
        self,
        descriptor: ProviderDescriptor,
        renderer: Callable[[ProviderContext], TemplateBundle],
    ) -> None:
        super().__init__(descriptor)
        self._renderer = renderer

    def plan(self, context: ProviderContext) -> TargetPlan:
        bundle = self._renderer(context)
        return TargetPlan(
            provider_id=self.descriptor.id,
            target_kind=self.descriptor.target_kind,
            source_root=self.descriptor.source_root,
            phases=("target_bootstrap", "target_validation"),
            generated_paths=tuple(sorted(bundle.files)),
        )

    def scaffold(self, context: ProviderContext, plan: TargetPlan) -> ProviderResult:
        del plan
        bundle = self._renderer(context)
        generated: list[str] = []
        blockers: list[ProviderBlocker] = []
        for relative, content in bundle.files.items():
            path = _safe_target(context.workspace, relative)
            if path.exists() and path.read_text(encoding="utf-8") != content:
                blockers.append(
                    ProviderBlocker(
                        code="generated_file_conflict",
                        message=f"Refusing to overwrite user-owned file: {relative}",
                        next_action=(
                            "Move or reconcile the conflicting file, then retry the "
                            "target_bootstrap phase."
                        ),
                    )
                )
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            generated.append(relative)
        state = (
            CapabilityEvidenceState.BLOCKED
            if blockers
            else CapabilityEvidenceState.PREPARED
        )
        return ProviderResult(
            provider_id=self.descriptor.id,
            target_kind=self.descriptor.target_kind,
            status=state,
            generated_files=tuple(generated),
            commands=bundle.bootstrap_commands,
            capabilities=tuple(
                CapabilityEvidence(
                    capability=name,
                    state=(
                        CapabilityEvidenceState.DECLARED
                        if supported
                        else CapabilityEvidenceState.UNSUPPORTED
                    ),
                    provider=self.descriptor.id,
                )
                for name, supported in sorted(self.descriptor.capabilities.items())
            ),
            blockers=tuple(blockers),
            content_hash=_bundle_hash(context.workspace, bundle.files),
        )

    def validate(self, context: ProviderContext, plan: TargetPlan) -> ProviderResult:
        del plan
        bundle = self._renderer(context)
        missing = [relative for relative in bundle.files if not (context.workspace / relative).is_file()]
        blockers = tuple(
            ProviderBlocker(
                code="generated_file_missing",
                message=f"Expected generated file is missing: {relative}",
                next_action="Retry target_bootstrap before validation.",
            )
            for relative in missing
        )
        return ProviderResult(
            provider_id=self.descriptor.id,
            target_kind=self.descriptor.target_kind,
            status=(
                CapabilityEvidenceState.BLOCKED
                if blockers
                else CapabilityEvidenceState.PREPARED
            ),
            commands=bundle.validation_commands,
            capabilities=self._capabilities(
                CapabilityEvidenceState.DECLARED
            ),
            blockers=blockers,
            content_hash=_bundle_hash(context.workspace, bundle.files),
        )


def provider_for_descriptor(descriptor: ProviderDescriptor):
    renderer = _RENDERERS.get((descriptor.target_kind, descriptor.id))
    if renderer is None:
        return DeclarativeTargetProvider(descriptor)
    return TemplateTargetProvider(descriptor, renderer)


def _react_native(context: ProviderContext) -> TemplateBundle:
    root = "apps/mobile"
    package = {
        "name": f"{context.slug}-mobile",
        "version": "0.1.0",
        "private": True,
        "main": "expo-router/entry",
        "scripts": {
            "start": "expo start",
            "android": "expo run:android",
            "prebuild:android": "expo prebuild --platform android --no-install",
            "typecheck": "tsc --noEmit && tsc -p ../../packages/codex-bridge-react-native/tsconfig.json",
            "lint": "eslint app src tests",
            "test": "node --test tests/*.test.mjs",
        },
        "dependencies": {
            "@codex/bridge-react-native": "file:../../packages/codex-bridge-react-native",
            "expo": "57.0.0",
            "expo-router": "57.0.8",
            "expo-status-bar": "3.0.9",
            "react": "19.2.8",
            "react-native": "0.86.0",
        },
        "devDependencies": {
            "@types/react": "19.2.14",
            "eslint": "9.39.2",
            "typescript": "5.9.3",
            "typescript-eslint": "8.66.0",
        },
    }
    app = {
        "expo": {
            "name": context.project_name,
            "slug": context.slug,
            "version": "0.1.0",
            "orientation": "default",
            "scheme": context.slug,
            "plugins": ["expo-router", "./plugins/with-preview-signing"],
            "experiments": {"typedRoutes": True},
            "android": {
                "package": f"com.nienfos.{_android_package_segment(context.slug)}",
                "versionCode": 1,
            },
            "extra": {
                "sourceApp": context.slug,
                "creationMode": "scaffold",
                "productRoutesEnabled": False,
            },
        }
    }
    files = {
        f"{root}/package.json": _json(package),
        f"{root}/app.json": _json(app),
        f"{root}/tsconfig.json": _json(
            {
                "extends": "expo/tsconfig.base",
                "compilerOptions": {"strict": True, "noEmit": True},
                "include": ["**/*.ts", "**/*.tsx", ".expo/types/**/*.ts"],
            }
        ),
        f"{root}/eslint.config.mjs": "import tseslint from 'typescript-eslint';\nexport default tseslint.config(...tseslint.configs.recommended, { languageOptions: { parserOptions: { ecmaFeatures: { jsx: true } } } });\n",
        f"{root}/app/_layout.tsx": "import { Stack } from 'expo-router';\nexport default function RootLayout() { return <Stack screenOptions={{ headerShown: false }} />; }\n",
        f"{root}/app/index.tsx": _expo_screen(context.slug),
        f"{root}/src/runtime.ts": _expo_runtime(context.slug),
        f"{root}/tests/scaffold.test.mjs": "import assert from 'node:assert/strict';\nimport test from 'node:test';\ntest('scaffold has no product routes', () => assert.equal(false, false));\n",
        f"{root}/plugins/with-preview-signing.js": _expo_signing_plugin(),
        "scripts/publish_android_preview_release.sh": _expo_publish_script(
            context.slug
        ),
        ".github/workflows/android-preview-release.yml": _expo_release_workflow(
            context.slug
        ),
        "packages/codex-bridge-react-native/package.json": _json(
            {
                "name": "@codex/bridge-react-native",
                "version": "0.1.0",
                "private": True,
                "type": "module",
                "main": "src/index.ts",
            }
        ),
        "packages/codex-bridge-react-native/src/index.ts": _react_native_bridge(),
        "packages/codex-bridge-react-native/tsconfig.json": _json(
            {
                "compilerOptions": {
                    "strict": True,
                    "target": "ES2022",
                    "module": "ESNext",
                    "moduleResolution": "Bundler",
                    "noEmit": True,
                },
                "include": ["src/**/*.ts"],
            }
        ),
    }
    return TemplateBundle(
        files=files,
        bootstrap_commands=(
            ("npm", "install"),
            ("npm", "run", "prebuild:android"),
            ("npm", "install", "--ignore-scripts"),
        ),
        validation_commands=(
            ("npm", "ci"),
            ("npm", "run", "typecheck"),
            ("npm", "run", "lint"),
            ("npm", "test"),
            ("npm", "run", "prebuild:android"),
            (
                "./android/gradlew",
                "-p",
                "android",
                "assembleDebug",
                "-PreactNativeArchitectures=arm64-v8a",
                "--max-workers=1",
                "--no-daemon",
            ),
        ),
    )


def _flutter(context: ProviderContext) -> TemplateBundle:
    root = "apps/mobile"
    files = {
        f"{root}/pubspec.yaml": f"name: {_dart_package(context.slug)}\ndescription: Neutral composable scaffold.\npublish_to: none\nversion: 0.1.0+1\nenvironment:\n  sdk: '>=3.4.0 <4.0.0'\ndependencies:\n  flutter:\n    sdk: flutter\ndev_dependencies:\n  flutter_test:\n    sdk: flutter\n  flutter_lints: 5.0.0\nflutter:\n  uses-material-design: true\n",
        f"{root}/lib/main.dart": _flutter_main(context.slug),
        f"{root}/test/scaffold_test.dart": "import 'package:flutter_test/flutter_test.dart';\nvoid main() { test('neutral scaffold contract', () { expect('scaffold_ready', isNotEmpty); }); }\n",
    }
    return TemplateBundle(
        files=files,
        bootstrap_commands=(
            (
                "flutter",
                "create",
                "--empty",
                "--org",
                "com.nienfos",
                "--platforms=android,ios",
                ".",
            ),
        ),
        validation_commands=(
            ("flutter", "pub", "get"),
            ("flutter", "analyze"),
            ("flutter", "test"),
            ("flutter", "build", "apk", "--debug"),
        ),
    )


def _flutter_web(context: ProviderContext) -> TemplateBundle:
    root = "apps/web"
    files = {
        f"{root}/pubspec.yaml": f"name: {_dart_package(context.slug)}_web\ndescription: Neutral composable web scaffold.\npublish_to: none\nversion: 0.1.0+1\nenvironment:\n  sdk: '>=3.4.0 <4.0.0'\ndependencies:\n  flutter:\n    sdk: flutter\ndev_dependencies:\n  flutter_test:\n    sdk: flutter\n  flutter_lints: 5.0.0\nflutter:\n  uses-material-design: true\n",
        f"{root}/lib/main.dart": _flutter_main(context.slug),
        f"{root}/test/scaffold_test.dart": "import 'package:flutter_test/flutter_test.dart';\nvoid main() { test('neutral web scaffold contract', () { expect('scaffold_ready', isNotEmpty); }); }\n",
    }
    return TemplateBundle(
        files=files,
        bootstrap_commands=(
            ("flutter", "create", "--empty", "--platforms=web", "."),
        ),
        validation_commands=(
            ("flutter", "pub", "get"),
            ("flutter", "analyze"),
            ("flutter", "test"),
            ("flutter", "build", "web"),
        ),
    )


def _sveltekit(context: ProviderContext) -> TemplateBundle:
    root = "apps/web"
    package = {
        "name": f"{context.slug}-web",
        "version": "0.1.0",
        "private": True,
        "type": "module",
        "scripts": {
            "dev": "vite dev",
            "build": "vite build",
            "preview": "vite preview",
            "check": "svelte-kit sync && svelte-check --tsconfig ./tsconfig.json",
            "lint": "eslint 'src/**/*.ts'",
            "test": "vitest run",
        },
        "devDependencies": {
            "@types/node": "26.2.0",
            "@sveltejs/adapter-cloudflare": "7.2.9",
            "@sveltejs/kit": "2.70.2",
            "@sveltejs/vite-plugin-svelte": "7.2.0",
            "eslint": "9.39.2",
            "svelte": "5.56.8",
            "svelte-check": "4.7.5",
            "typescript": "5.9.3",
            "typescript-eslint": "8.66.0",
            "vite": "8.2.1",
            "vitest": "4.1.10",
        },
    }
    files = {
        f"{root}/package.json": _json(package),
        f"{root}/svelte.config.js": "import adapter from '@sveltejs/adapter-cloudflare';\nexport default { kit: { adapter: adapter() } };\n",
        f"{root}/vite.config.ts": "import { sveltekit } from '@sveltejs/kit/vite';\nimport { defineConfig } from 'vite';\nexport default defineConfig({ plugins: [sveltekit()] });\n",
        f"{root}/eslint.config.js": "import tseslint from 'typescript-eslint';\nexport default tseslint.config(...tseslint.configs.recommended);\n",
        f"{root}/tsconfig.json": _json({"extends": "./.svelte-kit/tsconfig.json", "compilerOptions": {"strict": True}}),
        f"{root}/src/app.html": "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">%sveltekit.head%</head><body data-sveltekit-preload-data=\"hover\"><div style=\"display: contents\">%sveltekit.body%</div></body></html>\n",
        f"{root}/src/routes/+page.svelte": _svelte_page(context.slug),
        f"{root}/src/routes/+error.svelte": "<script lang=\"ts\">import { page } from '$app/state';</script>\n<svelte:head><title>Scaffold status</title></svelte:head>\n<main><h1>Technical route unavailable</h1><p>Status {page.status}</p></main>\n",
        f"{root}/src/lib/runtime.ts": _svelte_runtime(context.slug),
        f"{root}/src/lib/runtime.test.ts": "import { describe, expect, it } from 'vitest';\nimport { sourceApp } from './runtime';\ndescribe('runtime', () => it('has source app', () => expect(sourceApp.length).toBeGreaterThan(0)));\n",
        f"{root}/src/app.d.ts": "declare global { namespace App {} }\nexport {};\n",
    }
    return TemplateBundle(
        files=files,
        bootstrap_commands=(("npm", "install", "--ignore-scripts"),),
        validation_commands=(
            ("npm", "ci", "--ignore-scripts"),
            ("npm", "run", "check"),
            ("npm", "run", "lint"),
            ("npm", "test"),
            ("npm", "run", "build"),
        ),
    )


def _fastapi(context: ProviderContext) -> TemplateBundle:
    root = "services/api"
    requirements_lock = """annotated-types==0.8.0
anyio==4.14.2
certifi==2026.7.22
click==8.4.2
fastapi==0.116.1
h11==0.16.0
httpcore==1.0.9
httpx==0.28.1
idna==3.18
iniconfig==2.3.0
packaging==26.3
pluggy==1.6.0
pydantic==2.13.4
pydantic-core==2.46.4
pygments==2.20.0
pytest==8.4.1
starlette==0.47.3
typing-extensions==4.16.0
typing-inspection==0.4.2
uvicorn==0.35.0
"""
    files = {
        f"{root}/requirements.lock": requirements_lock,
        f"{root}/app/__init__.py": "",
        f"{root}/app/main.py": _fastapi_main(context.slug),
        f"{root}/tests/test_health.py": _fastapi_test(),
        f"{root}/Dockerfile": "FROM python:3.12.11-slim@sha256:73c2c30f7e62b8676c2bfbe6d7bb74aef4f2fe926010c87f6c4d9d3ef77ef6ad\nWORKDIR /app\nCOPY requirements.lock .\nRUN pip install --no-cache-dir --no-deps -r requirements.lock\nCOPY . .\nCMD [\"uvicorn\", \"app.main:app\", \"--host\", \"0.0.0.0\", \"--port\", \"8080\"]\n",
    }
    return TemplateBundle(
        files=files,
        validation_commands=(
            (
                "python3",
                "-m",
                "venv",
                ".venv",
            ),
            (
                ".venv/bin/python",
                "-m",
                "pip",
                "install",
                "--no-deps",
                "-r",
                "requirements.lock",
            ),
            (".venv/bin/python", "-m", "pytest", "-q"),
        ),
    )


def _go(context: ProviderContext) -> TemplateBundle:
    root = "services/api"
    module = f"github.com/generated/{context.slug}/api"
    files = {
        f"{root}/go.mod": f"module {module}\n\ngo 1.24.0\n",
        f"{root}/cmd/server/main.go": _go_main(module),
        f"{root}/internal/server/server.go": _go_server(context.slug),
        f"{root}/internal/server/server_test.go": _go_test(module),
        f"{root}/Dockerfile": "FROM golang:1.24.6-alpine AS build\nWORKDIR /src\nCOPY . .\nRUN CGO_ENABLED=0 go build -trimpath -o /api ./cmd/server\nFROM scratch\nCOPY --from=build /api /api\nENTRYPOINT [\"/api\"]\n",
    }
    return TemplateBundle(
        files=files,
        validation_commands=(
            ("gofmt", "-w", "cmd", "internal"),
            ("go", "test", "./..."),
            ("go", "vet", "./..."),
            ("go", "build", "-trimpath", "-o", "build/api", "./cmd/server"),
        ),
    )


def _safe_target(workspace: Path, relative: str) -> Path:
    path = (workspace / relative).resolve()
    try:
        path.relative_to(workspace.resolve())
    except ValueError as exc:
        raise ValueError(f"Generated path escapes workspace: {relative}") from exc
    return path


def _bundle_hash(workspace: Path, files: Mapping[str, str]) -> str | None:
    digest = hashlib.sha256()
    for relative in sorted(files):
        path = workspace / relative
        if not path.is_file():
            return None
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def _dart_package(slug: str) -> str:
    value = slug.replace("-", "_")
    return f"app_{value}" if value[:1].isdigit() else value


def _android_package_segment(slug: str) -> str:
    value = slug.replace("-", "")
    return f"app{value}" if value[:1].isdigit() else value


def _expo_screen(slug: str) -> str:
    return f"""import {{ StatusBar }} from 'expo-status-bar';
import {{ SafeAreaView, StyleSheet, Text, View }} from 'react-native';
import {{ runtime }} from '../src/runtime';

export default function TechnicalScaffold() {{
  return <SafeAreaView style={{styles.root}}><View style={{styles.panel}}>
    <Text accessibilityRole="header" style={{styles.title}}>Scaffold ready</Text>
    <Text>Technical bootstrap for {slug}</Text>
    <Text>Runtime: {{runtime.profile}}</Text><Text>Source: {{runtime.sourceApp}}</Text>
  </View><StatusBar style="auto" /></SafeAreaView>;
}}
const styles = StyleSheet.create({{
  root: {{ flex: 1, backgroundColor: '#f6f7f8', justifyContent: 'center', padding: 24 }},
  panel: {{ gap: 8, padding: 24, borderWidth: 1, borderColor: '#d7dadd', borderRadius: 12, backgroundColor: '#fff' }},
  title: {{ fontSize: 24, fontWeight: '600' }},
}});
"""


def _expo_runtime(slug: str) -> str:
    return f"""const required = (value: string | undefined, fallback: string): string => value?.trim() || fallback;
export const runtime = Object.freeze({{
  sourceApp: required(process.env.EXPO_PUBLIC_SOURCE_APP, '{slug}'),
  profile: required(process.env.EXPO_PUBLIC_RUNTIME_PROFILE, 'preview'),
  apiBaseUrl: process.env.EXPO_PUBLIC_API_BASE_URL?.trim() || null,
}});
"""


def _expo_signing_plugin() -> str:
    return r"""const { withAppBuildGradle } = require('expo/config-plugins');
module.exports = (config) => withAppBuildGradle(config, (next) => {
  if (next.modResults.language !== 'groovy') throw new Error('preview_signing_requires_groovy');
  let source = next.modResults.contents;
  const debugStart = 'signingConfigs {\n        debug {';
  const releaseConfig = `signingConfigs {\n        release {\n            storeFile file(System.getenv('ANDROID_KEYSTORE_PATH') ?: 'preview-upload-keystore.jks')\n            storePassword System.getenv('ANDROID_STORE_PASSWORD') ?: ''\n            keyAlias System.getenv('ANDROID_KEY_ALIAS') ?: 'preview'\n            keyPassword System.getenv('ANDROID_KEY_PASSWORD') ?: ''\n        }\n        debug {`;
  if (!source.includes(debugStart)) throw new Error('preview_signing_anchor_missing');
  source = source.replace(debugStart, releaseConfig);
  source = source.replace('release {\n            // Caution! In production, you need to generate your own keystore file.\n            // see https://reactnative.dev/docs/signed-apk-android.\n            signingConfig signingConfigs.debug', 'release {\n            signingConfig signingConfigs.release');
  next.modResults.contents = source;
  return next;
});
"""


def _expo_publish_script(slug: str) -> str:
    return f'''#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")/.." && pwd)"
cd "$ROOT_DIR"
watch=true
while [[ $# -gt 0 ]]; do
  case "$1" in --push) ;; --watch) watch=true ;; --no-watch) watch=false ;; *) echo "unknown argument: $1" >&2; exit 2 ;; esac
  shift
done
source_app="${{SOURCE_APP:-{slug}}}"
api_base_url="${{API_BASE_URL:-}}"
[[ "${{APP_RUNTIME_PROFILE:-}}" == "preview" ]] || {{ echo "APP_RUNTIME_PROFILE must be preview" >&2; exit 2; }}
[[ "${{API_RUNTIME:-}}" == "cloudflare_preview" ]] || {{ echo "API_RUNTIME must be cloudflare_preview" >&2; exit 2; }}
[[ "$api_base_url" == https://* ]] || {{ echo "API_BASE_URL must be a real HTTPS endpoint" >&2; exit 2; }}
[[ "$api_base_url" != *localhost* && "$api_base_url" != *127.0.0.1* && "$api_base_url" != *example.com* ]] || {{ echo "local or placeholder API is forbidden" >&2; exit 2; }}
[[ -f apps/mobile/package-lock.json ]] || {{ echo "Expo package lock is required" >&2; exit 2; }}
version="$(node -p "require('./apps/mobile/app.json').expo.version")"
build="$(node -p "require('./apps/mobile/app.json').expo.android.versionCode")"
tag="${{APP_ANDROID_PREVIEW_RELEASE_TAG:-android-preview-v${{version}}-build.${{build}}}}"
[[ -z "$(git status --porcelain)" ]] || {{ echo "working tree must be clean before tagging the preview release" >&2; exit 2; }}
origin="$(git remote get-url origin)"
repo="${{origin#https://github.com/}}"; repo="${{repo#git@github.com:}}"; repo="${{repo%.git}}"
gh repo view "$repo" >/dev/null
git rev-parse "refs/tags/$tag" >/dev/null 2>&1 || git tag "$tag"
git push origin "$tag"
if [[ "$watch" == true ]]; then
  gh release view "$tag" --repo "$repo" --json assets --jq '.assets[].name' | grep -Fx "$source_app.apk"
fi
'''


def _expo_release_workflow(slug: str) -> str:
    package_id = f"com.nienfos.{_android_package_segment(slug)}"
    return f'''name: Android preview release
on:
  push:
    tags:
      - "android-preview-v*"
permissions:
  contents: write
jobs:
  android:
    runs-on: ubuntu-latest
    env:
      APP_RUNTIME_PROFILE: preview
      API_RUNTIME: cloudflare_preview
      NODE_ENV: production
      EXPO_PUBLIC_RUNTIME_PROFILE: preview
      EXPO_PUBLIC_SOURCE_APP: {slug}
      EXPO_PUBLIC_API_BASE_URL: ${{{{ vars.API_BASE_URL }}}}
      ANDROID_KEY_ALIAS: ${{{{ secrets.ANDROID_KEY_ALIAS }}}}
      ANDROID_KEY_PASSWORD: ${{{{ secrets.ANDROID_KEY_PASSWORD }}}}
      ANDROID_STORE_PASSWORD: ${{{{ secrets.ANDROID_STORE_PASSWORD }}}}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22.18.0
          cache: npm
          cache-dependency-path: apps/mobile/package-lock.json
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "17"
      - uses: android-actions/setup-android@v3
      - name: Validate real release runtime
        run: |
          case "$EXPO_PUBLIC_API_BASE_URL" in https://*) ;; *) echo "API_BASE_URL must be a real HTTPS endpoint" >&2; exit 2 ;; esac
          case "$EXPO_PUBLIC_API_BASE_URL" in *localhost*|*127.0.0.1*|*example.com*) echo "local or placeholder API is forbidden" >&2; exit 2 ;; esac
      - run: npm ci
        working-directory: apps/mobile
      - run: npm run typecheck && npm run lint && npm test && npm run prebuild:android
        working-directory: apps/mobile
      - name: Configure stable signing
        run: |
          printf '%s' "${{{{ secrets.ANDROID_KEYSTORE_BASE64 }}}}" | base64 --decode > apps/mobile/android/app/preview-upload-keystore.jks
          echo "ANDROID_KEYSTORE_PATH=$GITHUB_WORKSPACE/apps/mobile/android/app/preview-upload-keystore.jks" >> "$GITHUB_ENV"
      - name: Build normalized APK
        run: ./gradlew assembleRelease --no-daemon --max-workers=1
        working-directory: apps/mobile/android
      - name: Verify signature and package identity
        run: |
          apk="apps/mobile/android/app/build/outputs/apk/release/app-release.apk"
          apksigner="$(find "$ANDROID_HOME/build-tools" -name apksigner -type f | sort -V | tail -n 1)"
          aapt="$(find "$ANDROID_HOME/build-tools" -name aapt -type f | sort -V | tail -n 1)"
          test -n "$apksigner" && test -n "$aapt"
          "$apksigner" verify --verbose --print-certs "$apk" | tee /tmp/apksigner.txt
          grep -q "Verified using" /tmp/apksigner.txt
          ! grep -Eqi 'CN=Android Debug|Android Debug' /tmp/apksigner.txt
          "$aapt" dump badging "$apk" | grep -F "package: name='{package_id}'"
      - name: Normalize artifact
        run: |
          cp apps/mobile/android/app/build/outputs/apk/release/app-release.apk "{slug}.apk"
          sha256sum "{slug}.apk" > "{slug}.apk.sha256"
      - name: Publish prerelease
        env:
          GH_TOKEN: ${{{{ github.token }}}}
        run: gh release create "${{{{ github.ref_name }}}}" "{slug}.apk" "{slug}.apk.sha256" --prerelease --title "${{{{ github.ref_name }}}}" --generate-notes
'''


def _react_native_bridge() -> str:
    return """export type Bounds = { x: number; y: number; width: number; height: number };
export type FeedbackItem = { id: string; comment: string; screenshotUri?: string; bounds?: Bounds; audioUri?: string; createdAt: string };
export type UpdateInfo = { version: string; build: number; apkUrl: string; sha256: string };
export interface FeedbackStorage { load(): Promise<readonly FeedbackItem[]>; save(items: readonly FeedbackItem[]): Promise<void>; }
export interface FeedbackCapture { screenshot(): Promise<string>; audio?(): Promise<string>; }
export type FeedbackSender = (items: readonly FeedbackItem[]) => Promise<void>;
export class FeedbackQueue {
  private constructor(private readonly storage: FeedbackStorage, private readonly items: FeedbackItem[]) {}
  static async create(storage: FeedbackStorage): Promise<FeedbackQueue> { return new FeedbackQueue(storage, [...await storage.load()]); }
  async enqueue(item: FeedbackItem): Promise<void> { this.items.push(item); await this.storage.save(this.items); }
  pending(): readonly FeedbackItem[] { return [...this.items]; }
  async sendBatch(send: FeedbackSender, releaseWhenComplete = false, release?: () => Promise<void>): Promise<void> {
    if (!this.items.length) return; await send(this.pending()); this.items.splice(0); await this.storage.save(this.items);
    if (releaseWhenComplete && release) await release();
  }
}
export const captureFeedback = async (capture: FeedbackCapture, comment: string, bounds?: Bounds, includeAudio = false): Promise<FeedbackItem> => ({ id: `${Date.now()}`, comment, bounds, screenshotUri: await capture.screenshot(), audioUri: includeAudio && capture.audio ? await capture.audio() : undefined, createdAt: new Date().toISOString() });
export const sendFeedbackBatch = async (bridgeUrl: string, sourceApp: string, items: readonly FeedbackItem[], request: typeof fetch = fetch): Promise<void> => { const response = await request(`${bridgeUrl.replace(/\\/$/, '')}/developer-feedback/batches`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ sourceApp, items }) }); if (!response.ok) throw new Error(`feedback_batch_failed:${response.status}`); };
export const workbenchDeepLink = (bridgeUrl: string, workspacePath: string) => `${bridgeUrl.replace(/\\/$/, '')}/sdd/workbench/view?workspace_path=${encodeURIComponent(workspacePath)}`;
export type Sha256 = (bytes: Uint8Array) => Promise<string>;
export const verifyChecksum = async (bytes: Uint8Array, expected: string, sha256: Sha256): Promise<boolean> => (await sha256(bytes)).toLowerCase() === expected.toLowerCase();
export interface AndroidInstaller { install(apkUri: string): Promise<void>; }
export const handoffUpdate = async (info: UpdateInfo, download: (url: string) => Promise<{ uri: string; bytes: Uint8Array }>, sha256: Sha256, installer: AndroidInstaller): Promise<void> => {
  const artifact = await download(info.apkUrl); if (!(await verifyChecksum(artifact.bytes, info.sha256, sha256))) throw new Error('update_checksum_mismatch'); await installer.install(artifact.uri);
};
"""


def _flutter_main(slug: str) -> str:
    return f"""import 'package:flutter/material.dart';
void main() => runApp(const ScaffoldApp());
class RuntimeConfiguration {{
  static const sourceApp = String.fromEnvironment('SOURCE_APP', defaultValue: '{slug}');
  static const profile = String.fromEnvironment('APP_RUNTIME_PROFILE', defaultValue: 'preview');
  static const apiBaseUrl = String.fromEnvironment('API_BASE_URL');
}}
class ScaffoldApp extends StatelessWidget {{
  const ScaffoldApp({{super.key}});
  @override Widget build(BuildContext context) => MaterialApp(
    title: 'Scaffold ready', home: Scaffold(body: Center(child: Semantics(
      label: 'Technical scaffold status', child: const Column(mainAxisSize: MainAxisSize.min, children: [Text('Scaffold ready'), Text('Source: ${{RuntimeConfiguration.sourceApp}}'), Text('Runtime: ${{RuntimeConfiguration.profile}}')])))
    )
  );
}}
"""


def _svelte_page(slug: str) -> str:
    return f"""<script lang="ts">import {{ sourceApp, runtimeProfile }} from '$lib/runtime';</script>
<svelte:head><title>Scaffold ready</title><meta name="robots" content="noindex" /></svelte:head>
<main><section aria-labelledby="title"><h1 id="title">Scaffold ready</h1><p>Technical bootstrap for {slug}</p><dl><dt>Source app</dt><dd>{{sourceApp}}</dd><dt>Runtime</dt><dd>{{runtimeProfile}}</dd></dl></section></main>
<style>:global(body){{margin:0;font-family:system-ui,sans-serif;background:#f6f7f8;color:#202428}}main{{min-height:100vh;display:grid;place-items:center;padding:1.5rem}}section{{width:min(36rem,100%);box-sizing:border-box;background:white;border:1px solid #d7dadd;border-radius:.75rem;padding:2rem}}h1{{margin-top:0}}dl{{display:grid;grid-template-columns:auto 1fr;gap:.5rem 1rem}}dt{{font-weight:600}}</style>
"""


def _svelte_runtime(slug: str) -> str:
    return f"""import {{ env }} from '$env/dynamic/public';
export const sourceApp = env.PUBLIC_SOURCE_APP?.trim() || '{slug}';
export const runtimeProfile = env.PUBLIC_RUNTIME_PROFILE?.trim() || 'preview';
export const apiBaseUrl = env.PUBLIC_API_BASE_URL?.trim() || null;
"""


def _fastapi_main(slug: str) -> str:
    return f'''from __future__ import annotations
import os
from uuid import uuid4
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

app = FastAPI(title="Scaffold API", version=os.getenv("APP_VERSION", "0.1.0"))

@app.middleware("http")
async def correlation(request: Request, call_next):
    correlation_id = request.headers.get("x-correlation-id") or str(uuid4())
    request.state.correlation_id = correlation_id
    response = await call_next(request)
    response.headers["x-correlation-id"] = correlation_id
    return response

@app.get("/health", operation_id="getHealth")
def health():
    return {{"status": "ok", "source_app": os.getenv("SOURCE_APP", "{slug}"), "version": os.getenv("APP_VERSION", "0.1.0")}}

@app.get("/version", operation_id="getVersion")
def version():
    return {{"source_app": os.getenv("SOURCE_APP", "{slug}"), "version": os.getenv("APP_VERSION", "0.1.0")}}

def error_payload(request: Request, code: str, message: str):
    return {{"error": {{"code": code, "message": message, "correlation_id": request.state.correlation_id}}}}

@app.exception_handler(StarletteHTTPException)
async def http_failure(request: Request, exc: StarletteHTTPException):
    code = "not_found" if exc.status_code == 404 else "request_error"
    message = "Route not found" if exc.status_code == 404 else "Request failed"
    return JSONResponse(status_code=exc.status_code, content=error_payload(request, code, message))

@app.exception_handler(Exception)
async def failure(request: Request, exc: Exception):
    del exc
    return JSONResponse(status_code=500, content=error_payload(request, "internal_error", "Request failed"))
'''


def _fastapi_test() -> str:
    return """from fastapi.testclient import TestClient
from app.main import app
def test_health_contract():
    response = TestClient(app).get('/health', headers={'x-correlation-id': 'test-id'})
    assert response.status_code == 200
    assert response.headers['x-correlation-id'] == 'test-id'
    assert set(response.json()) == {'status', 'source_app', 'version'}
def test_version_and_error_contract():
    client = TestClient(app)
    assert set(client.get('/version').json()) == {'source_app', 'version'}
    response = client.get('/missing', headers={'x-correlation-id': 'error-id'})
    assert response.status_code == 404
    assert response.headers['x-correlation-id'] == 'error-id'
    assert response.json() == {'error': {'code': 'not_found', 'message': 'Route not found', 'correlation_id': 'error-id'}}
"""


def _go_main(module: str) -> str:
    return f'''package main

import (
 "log"
 "net/http"
 "os"
 "{module}/internal/server"
)

func env(key, fallback string) string {{ if value := os.Getenv(key); value != "" {{ return value }}; return fallback }}
func main() {{ log.Fatal(http.ListenAndServe(":"+env("PORT", "8080"), server.New())) }}
'''


def _go_server(slug: str) -> str:
    return f'''package server

import (
 "encoding/json"
 "net/http"
 "os"
)

type healthResponse struct {{ Status string `json:"status"`; SourceApp string `json:"source_app"`; Version string `json:"version"` }}
type versionResponse struct {{ SourceApp string `json:"source_app"`; Version string `json:"version"` }}
type errorBody struct {{ Code string `json:"code"`; Message string `json:"message"`; CorrelationID string `json:"correlation_id"` }}
type errorResponse struct {{ Error errorBody `json:"error"` }}

func env(key, fallback string) string {{ if value := os.Getenv(key); value != "" {{ return value }}; return fallback }}
func correlation(next http.Handler) http.Handler {{ return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {{ id := r.Header.Get("X-Correlation-Id"); if id == "" {{ id = "generated" }}; r.Header.Set("X-Correlation-Id", id); w.Header().Set("X-Correlation-Id", id); next.ServeHTTP(w, r) }}) }}
func writeJSON(w http.ResponseWriter, value any) {{ w.Header().Set("Content-Type", "application/json"); _ = json.NewEncoder(w).Encode(value) }}
func writeError(w http.ResponseWriter, r *http.Request, status int, code, message string) {{ w.Header().Set("Content-Type", "application/json"); w.WriteHeader(status); _ = json.NewEncoder(w).Encode(errorResponse{{errorBody{{code, message, r.Header.Get("X-Correlation-Id")}}}}) }}
func getOnly(next http.HandlerFunc) http.HandlerFunc {{ return func(w http.ResponseWriter, r *http.Request) {{ if r.Method != http.MethodGet {{ writeError(w, r, http.StatusMethodNotAllowed, "request_error", "Request failed"); return }}; next(w, r) }} }}
func New() http.Handler {{ return correlation(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {{ switch r.URL.Path {{ case "/health": getOnly(func(w http.ResponseWriter, r *http.Request) {{ writeJSON(w, healthResponse{{"ok", env("SOURCE_APP", "{slug}"), env("APP_VERSION", "0.1.0")}}) }})(w, r); case "/version": getOnly(func(w http.ResponseWriter, r *http.Request) {{ writeJSON(w, versionResponse{{env("SOURCE_APP", "{slug}"), env("APP_VERSION", "0.1.0")}}) }})(w, r); default: writeError(w, r, http.StatusNotFound, "not_found", "Route not found") }} }})) }}
'''


def _go_test(module: str) -> str:
    return f'''package server_test

import (
 "encoding/json"
 "net/http"
 "net/http/httptest"
 "testing"
 "{module}/internal/server"
)

func request(t *testing.T, path string) (*httptest.ResponseRecorder, map[string]any) {{ t.Helper(); response := httptest.NewRecorder(); req := httptest.NewRequest(http.MethodGet, path, nil); req.Header.Set("X-Correlation-Id", "test-id"); server.New().ServeHTTP(response, req); var payload map[string]any; if err := json.Unmarshal(response.Body.Bytes(), &payload); err != nil {{ t.Fatal(err) }}; return response, payload }}
func TestHealthContract(t *testing.T) {{ response, payload := request(t, "/health"); if response.Code != 200 || response.Header().Get("X-Correlation-Id") != "test-id" || payload["status"] != "ok" {{ t.Fatalf("bad health: %#v", payload) }} }}
func TestVersionContract(t *testing.T) {{ response, payload := request(t, "/version"); if response.Code != 200 || payload["version"] == nil || payload["source_app"] == nil {{ t.Fatalf("bad version: %#v", payload) }} }}
func TestErrorContract(t *testing.T) {{ response, payload := request(t, "/missing"); if response.Code != 404 || response.Header().Get("X-Correlation-Id") != "test-id" {{ t.Fatalf("bad error: %#v", payload) }}; body := payload["error"].(map[string]any); if body["code"] != "not_found" || body["correlation_id"] != "test-id" {{ t.Fatalf("bad error: %#v", body) }} }}
'''


_RENDERERS: dict[tuple[TargetKind, str], Callable[[ProviderContext], TemplateBundle]] = {
    (TargetKind.MOBILE, "react_native_expo"): _react_native,
    (TargetKind.MOBILE, "flutter"): _flutter,
    (TargetKind.WEB, "flutter_web"): _flutter_web,
    (TargetKind.WEB, "sveltekit"): _sveltekit,
    (TargetKind.API, "fastapi"): _fastapi,
    (TargetKind.API, "go"): _go,
}
