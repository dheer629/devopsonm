#!/usr/bin/env bash
# Fetch and verify pinned components (sections 38, 65, 69).
#
# Build-time only. This script is never shipped inside the runtime payload and
# the operator's artifact never executes it (section 34).
#
#   build/fetch-components.sh [PLATFORM]     default: linux-amd64
set -euo pipefail

here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
lock=$here/components.lock.tsv
platform=${1:-linux-amd64}
cache=$here/cache/$platform
staged=$cache/staged
mkdir -p -- "$cache" "$staged"

die() { printf 'FETCH ERROR: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "build host needs $1"; }
need curl
need sha256sum

sha256() { sha256sum -- "$1" | awk '{print $1}'; }

fetched=0 skipped=0 recorded=0

while IFS=$'\t' read -r plat name version license url archive member sha binary status; do
    [[ -n ${plat:-} && $plat != \#* && $plat != platform ]] || continue
    [[ $plat == "$platform" ]] || continue

    if [[ $status == source-required || $url == SOURCE-REQUIRED ]]; then
        printf 'SKIP   %-9s no authoritative source pinned (status=%s)\n' "$name" "$status"
        skipped=$((skipped + 1)); continue
    fi

    suffix=bin; [[ $archive == raw ]] || suffix=$archive
    dl=$cache/$name-$version.$suffix
    if [[ ! -s $dl ]]; then
        printf 'GET    %-9s %s\n' "$name" "$url"
        curl -fL --retry 3 --connect-timeout 20 --max-time 600 -o "$dl.part" "$url" \
            || die "download failed: $name"
        mv -- "$dl.part" "$dl"
    else
        printf 'CACHE  %-9s %s\n' "$name" "$dl"
    fi

    actual=$(sha256 "$dl")
    if [[ $sha == RECORD-ON-FETCH ]]; then
        printf 'RECORD %-9s sha256=%s\n' "$name" "$actual"
        printf '       upstream publishes no clean digest; pin this value after review.\n'
        recorded=$((recorded + 1))
    elif [[ $actual != "$sha" ]]; then
        printf '\nSECURITY FAILURE\n\nEmbedded component failed integrity validation.\n' >&2
        printf '  component : %s\n  expected  : %s\n  actual    : %s\n' "$name" "$sha" "$actual" >&2
        exit 1
    else
        printf 'VERIFY %-9s sha256 OK\n' "$name"
    fi

    case $archive in
        raw) cp -- "$dl" "$staged/$binary";;
        tar.gz)
            [[ $member != - ]] || die "$name needs an explicit member path"
            tar -xzf "$dl" -C "$cache" -- "$member" || die "extract failed: $name"
            cp -- "$cache/$member" "$staged/$binary";;
        zip)
            need unzip
            unzip -p -- "$dl" "$member" > "$staged/$binary" || die "extract failed: $name";;
        *) die "unknown archive type: $archive";;
    esac
    chmod 755 -- "$staged/$binary"
    fetched=$((fetched + 1))
done < "$lock"

printf '\nfetched=%s skipped=%s recorded=%s\nstaged: %s\n' "$fetched" "$skipped" "$recorded" "$staged"
if ((recorded > 0)); then
    printf 'NOTE: %s component(s) carry unverified digests; release stays blocked until reviewed (section 87).\n' "$recorded"
fi
