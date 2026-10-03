#!/usr/bin/env bash
# Database fixtures share the main harness's local-cluster safety gate and labels.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
exec bash "$ROOT/devopssentinel-e2e/run-all.sh" --domain database "$@"
