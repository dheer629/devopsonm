#!/usr/bin/env bash
# Wrap the payload in a single self-extracting artifact (sections 18, 19, 82).
#
#   build/build-self-extracting.sh [PLATFORM]      default: linux-amd64
#
# Produces:
#   build/out/DevOpsSentinel_<version>_<platform>.run
#   build/out/devopssentinel                          (operator-facing name)
#   build/out/DevOpsSentinel_<version>_<platform>.run.sha256
set -euo pipefail

here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
root=$(cd -- "$here/.." && pwd)
platform=${1:-linux-amd64}
out=$here/out
payload=$out/payload-$platform.tar.gz
[[ -r $payload ]] || { printf 'run build/build-payload.sh %s first\n' "$platform" >&2; exit 1; }

tool_version=$(sed -n 's/^APP_VERSION="\(.*\)"/\1/p' "$root/DevOps_K8s_Sentinel_FINAL_GP.sh" | head -1)
[[ -n $tool_version ]] || { printf 'cannot read APP_VERSION\n' >&2; exit 1; }
command -v base64 >/dev/null 2>&1 || { printf 'build host needs base64\n' >&2; exit 1; }

work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
tar -xzf "$payload" -C "$work"
install -m 755 -- "$root/DevOps_K8s_Sentinel_FINAL_GP.sh" "$work/bin/devopssentinel-engine"
tar -czf "$work/bundle.tar.gz" -C "$work" bin

artifact=$out/DevOpsSentinel_${tool_version}_${platform}.run
mkdir -p -- "$out"
cp -- "$here/launcher.sh" "$artifact"

# The payload begins on the first line after the launcher, so the line number is
# derived from the launcher's own length (no marker line can drift).
payload_line=$(( $(wc -l < "$artifact") + 1 ))
sed -i \
    -e "s|__SNTL_VERSION__|$tool_version|g" \
    -e "s|__SNTL_PLATFORM__|$platform|g" \
    -e "s|^PAYLOAD_LINE=.*|PAYLOAD_LINE=$payload_line|" \
    "$artifact"

base64 -w 0 "$work/bundle.tar.gz" >> "$artifact"
printf '\n' >> "$artifact"
chmod 755 -- "$artifact"

cp -- "$artifact" "$out/devopssentinel"
sha256sum -- "$artifact" > "$artifact.sha256"

printf 'artifact : %s (%s)\n' "$artifact" "$(du -h "$artifact" | awk '{print $1}')"
printf 'operator : %s\n' "$out/devopssentinel"
printf 'sha256   : %s\n' "$(awk '{print $1}' "$artifact.sha256")"
