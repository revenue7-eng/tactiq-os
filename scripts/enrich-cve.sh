#!/usr/bin/env bash
# enrich-cve.sh — produce the kernel-triaged CVE report for a release dir.
#
# Runs the OE-core contrib improve_kernel_cve_report.py over the raw
# sbom-cve-check report, using the kernel compiled-sources SPDX and the
# linux-vulns database, to ignore CVEs in not-compiled kernel code and
# resolve version-not-in-range entries. Writes cve-rock5a.enriched.json
# next to the raw report and (idempotently) records its hash in SHA256SUMS.
#
# Producer-side verification step, run AFTER mk-release.sh. It does NOT
# modify the image; it only enriches the CVE verification artifact.
#
# Requires the kernel SPDX to include compiled sources, i.e. the build must
# have had:  SPDX_INCLUDE_COMPILED_SOURCES:pn-linux-yocto = "1"
#
# Usage: scripts/enrich-cve.sh <release-dir> [build-dir] [vulns-dir]
set -euo pipefail

REL_DIR="${1:?usage: enrich-cve.sh <release-dir> [build-dir] [vulns-dir]}"
BUILD_DIR="${2:-$HOME/build-rock5a-wrynose}"
VULNS_DIR="${3:-$HOME/vulns-master}"
KVER="6.18.24"

IMPROVE="$HOME/tactiq-build-wrynose/layers/openembedded-core/scripts/contrib/improve_kernel_cve_report.py"
RAW="$REL_DIR/cve-rock5a.sbom-cve-check.yocto.json"
SPDX="$BUILD_DIR/tmp/deploy/spdx/3.0.1/tactiq_rock5a/builds/build-linux-yocto.spdx.json"
OUT="$REL_DIR/cve-rock5a.enriched.json"

for f in "$IMPROVE" "$RAW" "$SPDX"; do
  [ -f "$f" ] || { echo "ERROR: missing input: $f" >&2; exit 1; }
done
[ -d "$VULNS_DIR" ] || { echo "ERROR: missing vulns datadir: $VULNS_DIR" >&2; exit 1; }

echo "==> enriching CVE report (kver=$KVER)"
echo "    raw=$RAW"
echo "    spdx=$SPDX"
echo "    vulns=$VULNS_DIR ($(find "$VULNS_DIR" -name 'CVE-*.json' | wc -l) CVE files)"

python3 "$IMPROVE" \
  --spdx "$SPDX" --datadir "$VULNS_DIR" \
  --old-cve-report "$RAW" --kernel-version "$KVER" \
  --new-cve-report "$OUT"

# Record hash in SHA256SUMS (bare filename, matching mk-release format); idempotent.
# Only when a SHA256SUMS already exists (standalone post-mk-release use). When
# invoked from inside mk-release before its SHA256SUMS pass, skip and let
# mk-release's own sorted glob hash this file — avoids a premature, partial,
# self-referential SHA256SUMS.
if [ -f "$REL_DIR/SHA256SUMS" ]; then
  (
    cd "$REL_DIR"
    tmp="$(mktemp)"
    grep -v '  cve-rock5a.enriched.json$' SHA256SUMS > "$tmp" 2>/dev/null || true
    sha256sum cve-rock5a.enriched.json >> "$tmp"
    mv -f "$tmp" SHA256SUMS
  )
  echo "==> wrote $OUT and recorded it in SHA256SUMS"
else
  echo "==> wrote $OUT (no SHA256SUMS yet; caller will hash it)"
fi
