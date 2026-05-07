#!/usr/bin/env bash
# Build tactiq-os release artifacts from a completed Yocto build.
#
# Usage:
#   ./build-rc-artifacts.sh <release-tag> <output-dir>
#
# Requires:
#   - completed bitbake of an image with cve-check and create-spdx classes
#   - bitbake on PATH (for buildinfo via `bitbake -e`)
#
# Produces in <output-dir>:
#   rootfs-rock5a.ext4, kernel-rock5a.bin, rk3588s-rock-5a.dtb
#   manifest-rock5a.txt, buildinfo-rock5a.json
#   sbom-image-rock5a.spdx.tar.zst, sbom-image-rock5a-aggregate.spdx.json
#   cve-manifest-rock5a.json, cve-image-rock5a.txt
#   cve-full-rock5a.json.gz, cve-full-rock5a.txt.gz
#   SHA256SUMS

set -euo pipefail

if [[ $# -ne 2 ]]; then
    echo "usage: $0 <release-tag> <output-dir>" >&2
    exit 2
fi

TAG="$1"
OUT="$2"
IMAGE="tactiq-image-dev"
MACHINE="tactiq-rock5a"   # Yocto MACHINE name — used in deploy paths
BOARD="rock5a"            # short board name — used in release artifact names

DEPLOY="${BUILDDIR:-$HOME/build-rock5a}/tmp-glibc/deploy/images/${MACHINE}"
LOGDIR="${BUILDDIR:-$HOME/build-rock5a}/tmp-glibc/log/cve"
SCRIPTDIR="$(cd "$(dirname "$0")" && pwd)"

mkdir -p "$OUT"
cd "$OUT"

echo "==> Stage 1: native Yocto artifacts (rename/symlink-resolve)"
cp -L "${DEPLOY}/${IMAGE}-${MACHINE}.rootfs.ext4"         "rootfs-${BOARD}.ext4"
cp -L "${DEPLOY}/Image-${MACHINE}.bin"                    "kernel-${BOARD}.bin"
cp -L "${DEPLOY}/rk3588s-rock-5a.dtb"                     "rk3588s-rock-5a.dtb"
cp -L "${DEPLOY}/${IMAGE}-${MACHINE}.rootfs.manifest"     "manifest-${BOARD}.txt"
cp -L "${DEPLOY}/${IMAGE}-${MACHINE}.rootfs.spdx.tar.zst" "sbom-image-${BOARD}.spdx.tar.zst"
cp -L "${DEPLOY}/${IMAGE}-${MACHINE}.rootfs.json"         "cve-manifest-${BOARD}.json"
cp -L "${DEPLOY}/${IMAGE}-${MACHINE}.rootfs.cve"          "cve-image-${BOARD}.txt"

echo "==> Stage 2: gzip cve-summary into cve-full"
gzip -c "${LOGDIR}/cve-summary"      > "cve-full-${BOARD}.txt.gz"
gzip -c "${LOGDIR}/cve-summary.json" > "cve-full-${BOARD}.json.gz"

echo "==> Stage 3: build buildinfo-${BOARD}.json from bitbake -e"
TMPENV="$(mktemp)"
bitbake -e "$IMAGE" > "$TMPENV"
python3 - "$TMPENV" "buildinfo-${BOARD}.json" << 'PYEOF'
import json
import re
import sys

env_path, out_path = sys.argv[1], sys.argv[2]
pattern = re.compile(r'^(?:export\s+)?([A-Za-z0-9_:.+-]+)="((?:[^"\\]|\\.)*)"\s*$')
out = {}
with open(env_path, encoding="utf-8", errors="replace") as fh:
    for line in fh:
        m = pattern.match(line)
        if not m:
            continue
        key, raw_val = m.group(1), m.group(2)
        val = raw_val.replace('\\"', '"').replace('\\\\', '\\').replace('\\$', '$')
        out[key] = val
with open(out_path, "w", encoding="utf-8") as fh:
    json.dump(out, fh, indent=4, sort_keys=True)
    fh.write("\n")
print(f"buildinfo: {len(out)} keys", file=sys.stderr)
PYEOF
rm -f "$TMPENV"

echo "==> Stage 4: aggregate SPDX"
SPDX_TMP="$(mktemp -d)"
zstd -d "$(readlink -f "${DEPLOY}/${IMAGE}-${MACHINE}.rootfs.spdx.tar.zst")" -c \
    | tar -xf - -C "$SPDX_TMP"
"${SCRIPTDIR}/spdx-aggregate.py" \
    "$SPDX_TMP" \
    "sbom-image-${BOARD}-aggregate.spdx.json" \
    "$TAG" \
    "${IMAGE}-${MACHINE}"
rm -rf "$SPDX_TMP"

echo "==> Stage 5: SHA256SUMS"
sha256sum \
    "rootfs-${BOARD}.ext4" \
    "kernel-${BOARD}.bin" \
    "rk3588s-rock-5a.dtb" \
    "manifest-${BOARD}.txt" \
    "buildinfo-${BOARD}.json" \
    "sbom-image-${BOARD}.spdx.tar.zst" \
    "sbom-image-${BOARD}-aggregate.spdx.json" \
    "cve-manifest-${BOARD}.json" \
    "cve-full-${BOARD}.json.gz" \
    "cve-full-${BOARD}.txt.gz" \
    "cve-image-${BOARD}.txt" \
    > SHA256SUMS

echo "==> Done. Artifacts in: $OUT"
ls -la "$OUT"
