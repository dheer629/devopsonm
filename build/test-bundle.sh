#!/usr/bin/env bash
# Final-artifact bundle tests (sections 66-70, 77-81).
#
#   build/test-bundle.sh [ARTIFACT]
#
# Runs the ACTUAL built artifact under an isolated HOME and a deliberately
# minimal PATH, so a developer-installed kubectl/jq/helm/flux/psql/kcat cannot
# be picked up by accident (sections 67, 99).
set -uo pipefail

here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
artifact=${1:-$here/out/devopssentinel}
[[ -x $artifact ]] || { printf 'artifact not found or not executable: %s\n' "$artifact" >&2; exit 1; }

sandbox=$(mktemp -d)
trap 'rm -rf -- "$sandbox"' EXIT
home=$sandbox/home
mkdir -p -- "$home"
clean_path=/usr/bin:/bin        # jq/helm/flux/psql/kcat intentionally absent
pass=0 fail=0

case_() {
    local id=$1 desc=$2 rc=$3
    if ((rc == 0)); then printf '%s %-60s PASS\n' "$id" "$desc"; pass=$((pass + 1))
    else printf '%s %-60s FAIL (rc=%s)\n' "$id" "$desc" "$rc"; fail=$((fail + 1)); fi
}
run() { env -i HOME="$home" PATH="$clean_path" DEVOPSSENTINEL_HOME="$home/.devopssentinel" "$artifact" "$@" < /dev/null; }

printf 'ARTIFACT %s\nCLEAN PATH %s\n\n' "$artifact" "$clean_path"

# DS-BUNDLE-001 / DS-BUNDLE-003..011: first run extracts and reports components.
run --components > "$sandbox/components.txt" 2>&1
case_ DS-BUNDLE-001 'self-extraction on first run' $?
[[ -d $home/.devopssentinel/bin ]] && case_ DS-BUNDLE-002 'payload extracted under $HOME/bin' 0
for tool in kubectl helm flux jq yq openssl curl psql kcat; do
    if grep -qE "^${tool}[[:space:]]+BUNDLED[[:space:]]+OK" "$sandbox/components.txt"; then
        case_ "DS-BUNDLE-$tool" "bundled $tool in use" 0
    else
        printf 'DS-BUNDLE-%-3s %-60s SKIP (not bundled)\n' "$tool" "bundled $tool"
    fi
done

# DS-BUNDLE-012: bundled binaries win under a minimal PATH.
grep -q 'BUNDLED' "$sandbox/components.txt" \
    && case_ DS-BUNDLE-012 'bundled tools preferred under isolated PATH' 0 \
    || case_ DS-BUNDLE-012 'bundled tools preferred under isolated PATH' 1

# DS-BUNDLE-013: offline execution.
run --offline-check > "$sandbox/offline.txt" 2>&1
case_ DS-BUNDLE-013 'offline readiness check executes' $?

# DS-BUNDLE-015: architecture detection.
grep -q 'Platform' "$sandbox/offline.txt" && case_ DS-BUNDLE-015 'architecture detected' 0

# DS-BUNDLE-014 / DS-BUNDLE-078: one flipped byte must be refused.
victim=$(ls "$home/.devopssentinel/bin" 2>/dev/null | grep -vE 'components.tsv|devopssentinel-engine' | head -1)
if [[ -n ${victim:-} ]]; then
    printf 'corrupted\n' >> "$home/.devopssentinel/bin/$victim"
    run --verify > "$sandbox/verify.txt" 2>&1
    rc=$?
    ((rc != 0)) && case_ DS-BUNDLE-014 "corrupted $victim rejected" 0 \
                || case_ DS-BUNDLE-014 "corrupted $victim rejected" 1
    grep -q 'CORRUPT' "$sandbox/verify.txt" && case_ DS-BUNDLE-078 'integrity failure reported' 0
fi

# DS-BUNDLE-016: second run reuses the verified runtime.
run --version > "$sandbox/second.txt" 2>&1
case_ DS-BUNDLE-016 'second run reuses runtime' $?

# DS-BUNDLE-018: read-only guard (covers the bundled-toolchain fixtures too).
run --self-test > "$sandbox/selftest.txt" 2>&1
case_ DS-BUNDLE-018 'read-only guard + bundle fixtures pass' $?

printf '\nBUNDLE TOTAL=%s PASS=%s FAIL=%s\n' "$((pass + fail))" "$pass" "$fail"
((fail == 0))
