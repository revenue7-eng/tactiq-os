#!/usr/bin/env bash
# mk-release.sh — assemble tactiq-os release artifacts from a completed
# Yocto *wrynose* build, with a single-build consistency guard.
#
# Replaces the scarthgap-era build-rc-artifacts.sh + spdx-aggregate.py,
# which assumed SPDX 2.2 (.spdx.tar.zst), the old cve-check outputs and the
# tmp-glibc/ deploy path — none of which exist under wrynose. Both old
# scripts should be deleted alongside this commit.
#
# wrynose facts this script is built on (verified against a real build):
#   - deploy path is  ${BUILDDIR}/tmp/deploy/images/${MACHINE}
#   - the SBOM is a single, self-contained SPDX 3.0.1 file:
#       ${IMAGE}-${MACHINE}.rootfs.spdx.json
#     The image SBOM already *is* the aggregate (software_Sbom + all
#     packages + files), so there is no per-recipe aggregation and no
#     .spdx.tar.zst to unpack — spdx-aggregate.py is obsolete.
#   - CVE posture lives in  ${IMAGE}-${MACHINE}.rootfs.sbom-cve-check.yocto.json
#     (sbom-cve-check replaced the removed cve-check class).
#
# Usage:
#   ./mk-release.sh <release-tag> <output-dir>
#
# Environment:
#   BUILDDIR             default ~/build-rock5a-wrynose
#   MACHINE              default tactiq-rock5a
#   IMAGE                default tactiq-image      (production release recipe;
#                        set IMAGE=tactiq-image-dev to test against a dev build)
#   BOARD                default rock5a            (short name in artifact names)
#   SKIP_BUILDINFO=1     skip the bitbake -e buildinfo capture (no build env)
#   ALLOW_MIXED_BUILD=1  downgrade the single-build guard to a warning. For dev
#                        mechanics testing ONLY — the output is NOT a valid
#                        release (manifest / SBOM / image may be from different
#                        builds).
#
# Produces in <output-dir>:
#   image-${BOARD}.wic.gz, image-${BOARD}.wic.bmap   (compressed image + bmap;
#       the raw .wic is ~9.8 GB and exceeds the GitHub 2 GB asset limit, so we
#       publish the .gz + .bmap — flash with: bmaptool copy image.wic.gz /dev/sdX)
#   kernel-${BOARD}.bin, rk3588s-rock-5a.dtb
#   manifest-${BOARD}.txt, testdata-${BOARD}.json, buildinfo-${BOARD}.json
#   sbom-${BOARD}.spdx.json                          (SPDX 3.0.1)
#   cve-${BOARD}.sbom-cve-check.yocto.json
#   bundle-${BOARD}.raucb                            (if a RAUC bundle exists)
#   SHA256SUMS

set -euo pipefail

if [[ $# -ne 2 ]]; then
    echo "usage: $0 <release-tag> <output-dir>" >&2
    exit 2
fi

TAG="$1"
OUT="$2"
BUILDDIR="${BUILDDIR:-$HOME/build-rock5a-wrynose}"
MACHINE="${MACHINE:-tactiq-rock5a}"
IMAGE="${IMAGE:-tactiq-image}"
BOARD="${BOARD:-rock5a}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VULNS_DIR="${VULNS_DIR:-$HOME/vulns-master}"

DEPLOY="${BUILDDIR}/tmp/deploy/images/${MACHINE}"
PREFIX="${IMAGE}-${MACHINE}.rootfs"

[[ -d "$DEPLOY" ]] || { echo "::error:: deploy dir not found: $DEPLOY" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Single-build consistency guard.
#
# The deploy dir accumulates artifacts from partial rebuilds (bitbake -C),
# and the per-type "latest" symlinks can straddle different builds — e.g. the
# manifest from build A while the SBOM and image are from build B. Shipping a
# manifest and SBOM that describe different rootfses is a silent integrity
# defect. We pin the timestamp of the image being released and require every
# rootfs-derived artifact to come from that same build, or abort.
# (Kernel and DTB have a separate deploy lifecycle and are taken as-is.)
# ---------------------------------------------------------------------------
ts_of() {  # echo the 14-digit build timestamp embedded in a resolved path
    local p; p="$(readlink -f "$1" 2>/dev/null || true)"
    [[ "$p" =~ rootfs-([0-9]{14}) ]] && echo "${BASH_REMATCH[1]}" || echo ""
}

WIC_LINK="${DEPLOY}/${PREFIX}.wic.gz"
[[ -e "$WIC_LINK" ]] || { echo "::error:: image not found: ${WIC_LINK}" >&2; exit 1; }
T="$(ts_of "$WIC_LINK")"
[[ -n "$T" ]] || { echo "::error:: cannot read build timestamp from ${WIC_LINK}" >&2; exit 1; }
echo "==> release build: ${T}  (IMAGE=${IMAGE}, MACHINE=${MACHINE})"

ROOTFS_ARTIFACTS=( wic.gz wic.bmap spdx.json sbom-cve-check.yocto.json manifest testdata.json )
mixed=0
for ext in "${ROOTFS_ARTIFACTS[@]}"; do
    got="$(ts_of "${DEPLOY}/${PREFIX}.${ext}")"
    if [[ "$got" != "$T" ]]; then
        echo "::warning:: ${PREFIX}.${ext} is from build '${got:-<missing>}', not ${T}" >&2
        mixed=1
    fi
done
if [[ "$mixed" == 1 ]]; then
    if [[ "${ALLOW_MIXED_BUILD:-0}" == 1 ]]; then
        echo "::warning:: rootfs artifacts span multiple builds — proceeding (ALLOW_MIXED_BUILD=1)." >&2
        echo "::warning:: THIS OUTPUT IS NOT A VALID RELEASE." >&2
    else
        echo "::error:: deploy is not from a single clean build (rootfs artifacts span builds)." >&2
        echo "::error:: cut the release from a clean build, or set ALLOW_MIXED_BUILD=1 to test mechanics." >&2
        exit 1
    fi
fi

mkdir -p "$OUT"; cd "$OUT"

copy() {  # copy <src-relative-to-deploy> <dest>  — resolves symlinks, asserts existence
    local src="${DEPLOY}/$1" dst="$2"
    [[ -e "$src" ]] || { echo "::error:: missing artifact: $src" >&2; exit 1; }
    cp -L "$src" "$dst"
    echo "    + $dst"
}

echo "==> collecting artifacts"
copy "${PREFIX}.wic.gz"                     "image-${BOARD}.wic.gz"
copy "${PREFIX}.wic.bmap"                   "image-${BOARD}.wic.bmap"
copy "Image-${MACHINE}.bin"                 "kernel-${BOARD}.bin"
copy "rk3588s-rock-5a.dtb"                  "rk3588s-rock-5a.dtb"
copy "${PREFIX}.manifest"                   "manifest-${BOARD}.txt"
copy "${PREFIX}.testdata.json"              "testdata-${BOARD}.json"
copy "${PREFIX}.spdx.json"                  "sbom-${BOARD}.spdx.json"
copy "${PREFIX}.sbom-cve-check.yocto.json"  "cve-${BOARD}.sbom-cve-check.yocto.json"

# RAUC OTA bundle — separate recipe, not in the image deploy by default.
RAUCB="$(find "${BUILDDIR}/tmp/deploy" -maxdepth 3 -name '*.raucb' 2>/dev/null | head -1 || true)"
if [[ -n "$RAUCB" ]]; then
    cp -L "$RAUCB" "bundle-${BOARD}.raucb"
    echo "    + bundle-${BOARD}.raucb  (from ${RAUCB})"
else
    echo "::warning:: no RAUC .raucb found under ${BUILDDIR}/tmp/deploy — OTA bundle skipped." >&2
fi

# buildinfo — full bitbake datastore snapshot (distro / layers / versions /
# SRCREVs). Provenance and reproducibility input; needs the build env sourced.
if [[ "${SKIP_BUILDINFO:-0}" == 1 ]]; then
    echo "::warning:: SKIP_BUILDINFO=1 — buildinfo-${BOARD}.json omitted." >&2
elif command -v bitbake >/dev/null 2>&1; then
    echo "==> buildinfo (bitbake -e ${IMAGE})"
    TMPENV="$(mktemp)"; bitbake -e "$IMAGE" > "$TMPENV"
    python3 - "$TMPENV" "buildinfo-${BOARD}.json" <<'PYEOF'
import json, re, sys
env, out = sys.argv[1], sys.argv[2]
pat = re.compile(r'^(?:export\s+)?([A-Za-z0-9_:.+-]+)="((?:[^"\\]|\\.)*)"\s*$')
d = {}
for line in open(env, encoding="utf-8", errors="replace"):
    m = pat.match(line)
    if m:
        d[m.group(1)] = (m.group(2).replace('\\"', '"')
                                   .replace('\\\\', '\\')
                                   .replace('\\$', '$'))
json.dump(d, open(out, "w", encoding="utf-8"), indent=4, sort_keys=True)
open(out, "a", encoding="utf-8").write("\n")
print(f"buildinfo: {len(d)} keys", file=sys.stderr)
PYEOF
    rm -f "$TMPENV"
    echo "    + buildinfo-${BOARD}.json"
else
    echo "::error:: bitbake not on PATH — source the build env or set SKIP_BUILDINFO=1." >&2
    exit 1
fi


# ---------------------------------------------------------------------------
# Enriched CVE report — kernel-triaged posture via enrich-cve.sh. Runs BEFORE
# the SHA256SUMS pass so the enriched file is picked up by the sorted glob
# below. Graceful skip only when the external linux-vulns snapshot is absent
# (e.g. CI without it); a missing kernel SPDX / improve script / raw report is
# a real build defect and aborts (enrich-cve.sh exits non-zero under set -e).
# ---------------------------------------------------------------------------
echo "==> enriched CVE report"
if [[ -d "$VULNS_DIR" ]]; then
    "${SCRIPT_DIR}/enrich-cve.sh" "$OUT" "$BUILDDIR" "$VULNS_DIR"
    echo "    + cve-${BOARD}.enriched.json"
else
    echo "::warning:: vulns datadir ${VULNS_DIR} absent — enriched CVE report skipped (set VULNS_DIR or fetch linux-vulns)." >&2
fi
echo "==> SHA256SUMS"
# SHA256SUMS does not exist yet, so the glob below cannot include it.
shopt -s nullglob; files=( * ); shopt -u nullglob
[[ ${#files[@]} -gt 0 ]] || { echo "::error:: no artifacts to hash" >&2; exit 1; }
sha256sum -- "${files[@]}" | LC_ALL=C sort -k2 > SHA256SUMS

echo "==> done: ${OUT}  (tag ${TAG})"
ls -la "$OUT"
