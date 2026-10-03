#!/usr/bin/env bash
# Run every test layer for DevOpsSentinel Web.
set -uo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT" || exit 1

PYTHON_BIN=${PYTHON:-python3}
command -v "$PYTHON_BIN" >/dev/null 2>&1 || PYTHON_BIN=python
NPM=npm
command -v pnpm >/dev/null 2>&1 && NPM=pnpm
RC=0

printf '\n=== Backend tests (pytest) ===\n'
"$PYTHON_BIN" -m pytest -q || RC=1

printf '\n=== Frontend typecheck ===\n'
(cd frontend && "$NPM" run typecheck) || RC=1

printf '\n=== Frontend unit tests (vitest) ===\n'
(cd frontend && "$NPM" run test) || RC=1

printf '\n=== Frontend E2E + accessibility (playwright) ===\n'
(cd frontend && "$NPM" run e2e) || RC=1

if ((RC == 0)); then
    printf '\nALL TEST LAYERS PASSED\n'
else
    printf '\nTEST FAILURES PRESENT\n' >&2
fi
exit "$RC"
