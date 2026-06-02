#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PUBSPEC_PATH="$ROOT_DIR/frontend/mobile_app/pubspec.yaml"

if [[ ! -f "$PUBSPEC_PATH" ]]; then
  echo "No se encontro $PUBSPEC_PATH" >&2
  exit 1
fi

if ! git -C "$ROOT_DIR" diff --quiet || ! git -C "$ROOT_DIR" diff --cached --quiet; then
  echo "Hay cambios sin commit. Hace commit antes de publicar el release." >&2
  exit 1
fi

VERSION="$(awk '/^version:/ { print $2; exit }' "$PUBSPEC_PATH")"

if [[ -z "$VERSION" ]]; then
  echo "No pude leer la version desde $PUBSPEC_PATH" >&2
  exit 1
fi

TAG="android-v${VERSION//+/-build.}"
PUSH_TAG=false

if [[ "${1:-}" == "--push" ]]; then
  PUSH_TAG=true
fi

if git -C "$ROOT_DIR" rev-parse "$TAG" >/dev/null 2>&1; then
  echo "El tag $TAG ya existe." >&2
  exit 1
fi

git -C "$ROOT_DIR" tag -a "$TAG" -m "Android release $VERSION"

echo "Tag creado: $TAG"

if [[ "$PUSH_TAG" == true ]]; then
  git -C "$ROOT_DIR" push origin "$TAG"
  echo "Tag enviado. GitHub Actions va a compilar y publicar el APK en Releases."
else
  echo "Para publicar en GitHub ejecuta:"
  echo "  git push origin $TAG"
fi
