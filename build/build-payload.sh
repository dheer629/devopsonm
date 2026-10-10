#!/usr/bin/env bash
# Assemble the runtime payload: bin/ + components.tsv + release-manifest.json.
# Sections 21, 22, 41, 42, 64.
#
#   build/build-payload.sh [PLATFORM]        default: linux-amd64
set -euo pipefail

here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
lock=$here/components.lock.tsv
platform=${1:-linux-amd64}
staged=$here/cache/$platform/staged
out=$here/out
payload=$out/payload-$platform
tool_version=$(sed -n 's/^APP_VERSION="\(.*\)"/\1/p' "$here/../DevOps_K8s_Sentinel_FINAL_GP.sh" | head -1)

die() { printf 'PAYLOAD ERROR: %s\n' "$*" >&2; exit 1; }
[[ -d $staged ]] || die "run build/fetch-components.sh $platform first"
command -v sha256sum >/dev/null 2>&1 || die "build host needs sha256sum"

rm -rf -- "$payload"
mkdir -p -- "$payload/bin"

manifest=$payload/bin/components.tsv
printf '# COMPONENT\tVERSION\tSHA256\tLICENSE\tSOURCE\n' > "$manifest"
copied=0
while IFS=$'\t' read -r plat name version license url archive member sha binary status; do
    [[ -n ${plat:-} && $plat != \#* && $plat != platform ]] || continue
    [[ $plat == "$platform" ]] || continue
    [[ -x $staged/$binary ]] || { printf 'absent %-9s (not bundled)\n' "$name"; continue; }
    digest=$(sha256sum -- "$staged/$binary" | awk '{print $1}')
    # The manifest digest is the *extracted* binary, which is what the runtime
    # verifies before every execution (section 22).
    printf '%s\t%s\t%s\t%s\t%s\n' "$name" "$version" "$digest" "$license" "$url" >> "$manifest"
    install -m 755 -- "$staged/$binary" "$payload/bin/$binary"
    copied=$((copied + 1))
done < "$lock"
chmod 755 -- "$payload/bin"
chmod 644 -- "$manifest"

[[ $copied -gt 0 ]] || die "no components staged; nothing to bundle"

tar -czf "$out/payload-$platform.tar.gz" -C "$payload" bin
printf 'payload: %s (%s components, %s)\n' "$out/payload-$platform.tar.gz" "$copied" \
    "$(du -h "$out/payload-$platform.tar.gz" | awk '{print $1}')"

# release-manifest.json (section 64) for archival / reproducibility records.
json=$out/release-manifest.json
{
    printf '{\n  "schemaVersion": "1",\n  "toolVersion": "%s",\n  "platform": "%s",\n' "$tool_version" "$platform"
    printf '  "componentManifestVersion": "1",\n  "components": [\n'
    first=1
    while IFS=$'\t' read -r name version digest license source; do
        [[ $name != \#* ]] || continue
        ((first)) || printf ',\n'; first=0
        printf '    {"name": "%s", "version": "%s", "sha256": "%s", "license": "%s", "source": "%s"}' \
            "$name" "$version" "$digest" "$license" "$source"
    done < "$manifest"
    printf '\n  ]\n}\n'
} > "$json"
printf 'manifest: %s\n' "$json"
