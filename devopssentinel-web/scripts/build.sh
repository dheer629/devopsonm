#!/usr/bin/env bash
# Production build for DevOpsSentinel Web.
#   ./scripts/build.sh [--skip-tests]
set -uo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT" || exit 1
SKIP_TESTS=0
[[ "${1:-}" == "--skip-tests" ]] && SKIP_TESTS=1

step() { printf '\n=== %s ===\n' "$1"; }
fail() { printf 'BUILD FAILED: %s\n' "$1" >&2; exit 1; }

PYTHON_BIN=${PYTHON:-python3}
command -v "$PYTHON_BIN" >/dev/null 2>&1 || PYTHON_BIN=python

NPM=npm
command -v pnpm >/dev/null 2>&1 && NPM=pnpm

step "Frontend dependencies"
(cd frontend && "$NPM" install --no-audit --no-fund) || fail "frontend install"

step "Typecheck"
(cd frontend && "$NPM" run typecheck) || fail "typecheck"

step "Backend tests"
"$PYTHON_BIN" -m pytest -q || fail "backend tests"

if ((SKIP_TESTS == 0)); then
    step "Frontend tests"
    (cd frontend && "$NPM" run test) || fail "frontend tests"
fi

step "Frontend production build"
(cd frontend && "$NPM" run build) || fail "frontend build"
[[ -f frontend/dist/index.html ]] || fail "frontend dist missing"

step "Package"
bash scripts/package.sh || fail "package"

printf '\nBUILD OK -- run ./devopssentinel-web\n'
