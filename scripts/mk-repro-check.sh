#!/usr/bin/env bash
# mk-repro-check.sh — compare two independent release builds of the same tag
# and emit a dated per-file reproducibility report.
#
# Why this is a separate script
# -----------------------------
# mk-release.sh is single-build by design — it carries an explicit guard
# against assembling a release from mixed builds. Reproducibility is a
# two-build property, so it cannot live inside that script without defeating
# that guard. This wrapper runs *after* two independent invocations of
# mk-release.sh, each into its own output directory:
#
#   ./mk-release.sh v2.1.0-rc7 /tmp/rel-A      # build 1
#   (wipe TMPDIR / sstate as your reproducibility protocol requires, rebuild)
#   ./mk-release.sh v2.1.0-rc7 /tmp/rel-B      # build 2
#   ./mk-repro-check.sh /tmp/rel-A /tmp/rel-B v2.1.0-rc7
#
# Output goes to docs/reproducibility/ in the repo tree — NOT into the
# release asset set. The asset set's SHA256SUMS is sealed when mk-release.sh
# finishes; the report only exists after the second build, so adding it to
# the assets would mean regenerating SHA256SUMS after signing. The report is
# documentation, committed to the repo, and is referenced from the release
# notes by path.
#
# This wrapper never deletes or rewrites an existing report — mk-repro-report.py
# aborts if the target date already has one. A later measurement is a new
# dated report beside the old one.
#
# Usage:
#   ./mk-repro-check.sh <release-dir-A> <release-dir-B> <release-tag>
#
# Environment:
#   BOARD      default rock5a   (matches mk-release.sh)
#   DISTRO     default wrynose  (Yocto series; names the report file)
#   OUTDIR     default <repo>/docs/reproducibility
#   DATE       default today    (YYYY-MM-DD; set to re-date a report)

set -euo pipefail

if [[ $# -ne 3 ]]; then
    echo "usage: $0 <release-dir-A> <release-dir-B> <release-tag>" >&2
    exit 2
fi

DIR_A="$1"
DIR_B="$2"
TAG="$3"
BOARD="${BOARD:-rock5a}"
DISTRO="${DISTRO:-wrynose}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTDIR="${OUTDIR:-${SCRIPT_DIR}/../docs/reproducibility}"
DATE="${DATE:-$(date -u +%Y-%m-%d)}"

GEN="${SCRIPT_DIR}/mk-repro-report.py"
[[ -x "$GEN" || -f "$GEN" ]] || {
    echo "::error:: generator not found: $GEN" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Input validation. Both directories must be complete release sets for the
# SAME tag. Comparing a complete build against a partial one silently
# understates divergence, so every check below is a hard failure.
# ---------------------------------------------------------------------------
for d in "$DIR_A" "$DIR_B"; do
    [[ -d "$d" ]] || { echo "::error:: not a directory: $d" >&2; exit 1; }
    for f in "sbom-${BOARD}.spdx.json" "SHA256SUMS" "coverage-${BOARD}.${TAG}.yaml"; do
        [[ -f "${d}/${f}" ]] || {
            echo "::error:: ${d}: missing ${f} — not a complete ${TAG} release set" >&2
            exit 1; }
    done
done

if [[ "$(readlink -f "$DIR_A")" == "$(readlink -f "$DIR_B")" ]]; then
    echo "::error:: both arguments point at the same directory" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Top-level artifact hashes, read from each build's own SHA256SUMS. These are
# the coarse check: if the image and bundle hashes already match, per-file
# divergence can only be inside artifacts excluded from those files. We pass
# them through so the report states them explicitly rather than leaving the
# reader to diff two SHA256SUMS by eye.
#
# The coverage manifest is copied from the repo tree into both release sets,
# so it is identical by construction and carries no information about build
# reproducibility. Excluded to keep the artifact table honest.
# ---------------------------------------------------------------------------
artifact_args() {
    local dir="$1" flag="$2" name hash
    while read -r hash name; do
        case "$name" in
            SHA256SUMS|coverage-*) continue ;;
        esac
        printf '%s\n%s=%s\n' "$flag" "$name" "$hash"
    done < "${dir}/SHA256SUMS"
}

mapfile -t ART_A < <(artifact_args "$DIR_A" --artifact-a)
mapfile -t ART_B < <(artifact_args "$DIR_B" --artifact-b)

# ---------------------------------------------------------------------------
# Build identity. buildinfo-<board>.json is produced by mk-release.sh from
# `bitbake -e`; when SKIP_BUILDINFO=1 was used it will be absent, in which
# case we fall back to the directory name rather than inventing a timestamp.
# ---------------------------------------------------------------------------
build_id() {
    local dir="$1" bi="${1}/buildinfo-${BOARD}.json"
    if [[ -f "$bi" ]] && command -v python3 >/dev/null 2>&1; then
        python3 - "$bi" <<'PY' 2>/dev/null || basename "$dir"
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    raise SystemExit(1)
# BitBake sets DATETIME = "${DATE}${TIME}" (YYYYMMDDHHMMSS) and
# BUILDNAME ?= "${DATETIME}". Neither is a TactiQ variable; both come
# straight from bitbake.conf, so they are present in any buildinfo
# produced without SKIP_BUILDINFO=1. DATE+TIME is the fallback for a
# datastore where BUILDNAME was overridden and DATETIME excluded.
for k in ("DATETIME", "BUILDNAME"):
    v = d.get(k)
    if v:
        print(v)
        break
else:
    if d.get("DATE") and d.get("TIME"):
        print(d["DATE"] + d["TIME"])
    else:
        raise SystemExit(1)
PY
    else
        basename "$dir"
    fi
}

ID_A="$(build_id "$DIR_A")"
ID_B="$(build_id "$DIR_B")"

if [[ "$ID_A" == "$ID_B" ]]; then
    echo "::warning:: both builds report the same build id (${ID_A}) — are these" \
         "really two independent builds?" >&2
fi

echo "==> comparing ${DIR_A} against ${DIR_B}  (tag ${TAG})"
echo "    build A: ${ID_A}"
echo "    build B: ${ID_B}"

mkdir -p "$OUTDIR"

python3 "$GEN" \
    --sbom-a  "${DIR_A}/sbom-${BOARD}.spdx.json" \
    --sbom-b  "${DIR_B}/sbom-${BOARD}.spdx.json" \
    --release "$TAG" \
    --distro  "$DISTRO" \
    --machine "$BOARD" \
    --build-id-a "$ID_A" \
    --build-id-b "$ID_B" \
    --outdir  "$OUTDIR" \
    --date    "$DATE" \
    "${ART_A[@]}" "${ART_B[@]}"

echo
echo "==> commit the two files above; reference the .md from the release notes."
echo "    Do NOT edit an earlier report to agree with this one — a superseded"
echo "    report is evidence of what was measured then."
