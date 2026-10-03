#!/usr/bin/env bash
# Produce a self-contained local package of DevOpsSentinel Web.
set -uo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT" || exit 1

VERSION="1.0.0"
OUT="$ROOT/dist-package"
STAGE="$OUT/devopssentinel-web-$VERSION"

rm -rf "$OUT"
mkdir -p "$STAGE"

# Backend source (no caches, no virtualenvs).
mkdir -p "$STAGE/backend"
(cd backend && find app -type f -name '*.py' -print0 | tar --null -cf - -T -) | (cd "$STAGE/backend" && tar -xf -)
cp backend/requirements.txt "$STAGE/backend/"
mkdir -p "$STAGE/backend/tests"
cp -r backend/tests/. "$STAGE/backend/tests/"

# Built frontend.
mkdir -p "$STAGE/frontend"
cp -r frontend/dist "$STAGE/frontend/dist"

# Launcher, scripts, docs.
cp devopssentinel-web "$STAGE/"
cp -r scripts "$STAGE/scripts"
mkdir -p "$STAGE/docs"
cp -r docs/. "$STAGE/docs/" 2>/dev/null || true
cp README.md pyproject.toml "$STAGE/" 2>/dev/null || true

chmod +x "$STAGE/devopssentinel-web" "$STAGE/scripts/"*.sh 2>/dev/null || true

(cd "$OUT" && tar -czf "devopssentinel-web-$VERSION.tar.gz" "devopssentinel-web-$VERSION")
printf 'Package written to %s\n' "$OUT/devopssentinel-web-$VERSION.tar.gz"
