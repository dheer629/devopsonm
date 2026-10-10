#!/usr/bin/env bash
# DevOpsSentinel self-extracting launcher (sections 18, 19, 41-43, 81).
#
#   chmod +x devopssentinel && ./devopssentinel
#
# One file, one command. The embedded payload is verified before first use and
# reused afterwards. Nothing is written outside $HOME; no sudo, no package
# installation, no internet access is required (sections 17, 34, 98).
set -euo pipefail

SNTL_VERSION="__SNTL_VERSION__"
SNTL_PLATFORM="__SNTL_PLATFORM__"
PAYLOAD_LINE=0

die() { printf 'devopssentinel: %s\n' "$*" >&2; exit 1; }

# ------------------------------------------------------------- platform (81)
os=$(uname -s 2>/dev/null || printf unknown)
arch=$(uname -m 2>/dev/null || printf unknown)
case $arch in x86_64|amd64) arch=amd64;; aarch64|arm64) arch=arm64;; esac
detected="${os,,}-$arch"
if [[ $detected != "$SNTL_PLATFORM" ]]; then
    printf 'UNSUPPORTED PLATFORM\n\nOS:            %s\nArchitecture:  %s\nDetected:      %s\nSupported:     %s\n' \
        "$os" "$arch" "$detected" "$SNTL_PLATFORM" >&2
    exit 5
fi

home=${DEVOPSSENTINEL_HOME:-${HOME:?}/.devopssentinel}
runtime_root=$home/runtime
bin=$home/bin
mkdir -p -- "$home" "$runtime_root"
chmod 700 -- "$home" "$runtime_root" 2>/dev/null || :

# ------------------------------------------------------ reuse or extract (80)
if [[ -x $bin/devopssentinel-engine && -r $bin/components.tsv ]]; then
    reuse=1
else
    reuse=0
fi

if ((reuse == 0)); then
    command -v sha256sum >/dev/null 2>&1 || die "sha256sum is required to verify the payload"
    staging=$(mktemp -d "$runtime_root/session.XXXXXXXX") || die "cannot create a staging directory"
    trap 'rm -rf -- "$staging"' EXIT INT TERM
    tail -n +"$PAYLOAD_LINE" "$0" | base64 -d | tar -xzf - -C "$staging" \
        || die "payload extraction failed"
    [[ -r $staging/bin/components.tsv ]] || die "payload is missing components.tsv"

    # Every embedded binary is verified before it is ever executed (section 22).
    failed=0
    while IFS=$'\t' read -r name version digest license source; do
        [[ -n ${name:-} && $name != \#* ]] || continue
        file=$staging/bin/$name
        [[ -f $file ]] || continue
        actual=$(sha256sum -- "$file" | awk '{print $1}')
        if [[ $actual != "$digest" ]]; then
            printf 'SECURITY FAILURE\n\nEmbedded component failed integrity validation.\n  component : %s\n  expected  : %s\n  actual    : %s\n' \
                "$name" "$digest" "$actual" >&2
            failed=1
        fi
    done < "$staging/bin/components.tsv"
    ((failed == 0)) || exit 6

    chmod 755 -- "$staging/bin"/* 2>/dev/null || :
    # Atomic publish (section 42): a crash never leaves a partial runtime.
    rm -rf -- "$bin.new"
    mv -- "$staging/bin" "$bin.new"
    rm -rf -- "$bin"
    mv -- "$bin.new" "$bin"
fi

engine=$bin/devopssentinel-engine
[[ -r $engine ]] || die "engine not found in $bin"

export DEVOPSSENTINEL_HOME=$home
export SNTL_OUTPUT_DIR=$home
export PATH="$bin:$PATH"        # process-local only (sections 17, 72)
exec bash "$engine" "$@"
