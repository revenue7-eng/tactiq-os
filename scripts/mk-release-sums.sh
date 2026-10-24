#!/usr/bin/env bash
# mk-release-sums.sh: write the SHA256SUMS of a release, last.
#
# Usage: mk-release-sums.sh <release-tag> <output-dir>
#
# Release order (RELEASE_INTEGRITY.md):
#   1. scripts/mk-release.sh <tag> <dir>       artifacts, RIM, no SHA256SUMS
#   2. the release image on the reference device, cold start, envelopes
#   3. scripts/mk-l3-evidence.sh <tag> ...      signed evidence archive in <dir>
#   4. VERIFY-L3-<rcN>.md copied into <dir>; scripts/verify-l3.sh is
#      copied by this script (or must already be there, identical)
#   5. this script                              SHA256SUMS over all of it
# The release workflow signs SHA256SUMS with Sigstore, so the evidence, the
# procedure and the script are covered by that signature as well as the
# evidence list being signed under the release root.
#
# Before writing, the script checks that the three L3 files are present and
# that the archive's own list verifies to VERIFY_ROOT_CA with the Evidence
# Signer purpose. After writing, it runs verify-l3.sh on the output
# directory with this release's tag and board and requires exit status 0.
# From rc15 every release carries the same verify-l3.sh under that name;
# releases up to rc14 carry their own verify-l3-<rcN>.sh.
#
# Environment:
#   VERIFY_ROOT_CA  the release root certificate (required unless ALLOW_NO_L3=1)
#   BOARD           board name, as for mk-release.sh (default rock5a): the RIM
#                   is rim-<BOARD>.json
#   VERIFY_ROOT_FILE  name the release root carries in the release (default
#                   release-root-r2.pem)
#   VERIFY_ROOT_FP  SHA-256 fingerprint verify-l3.sh pins the root to
#                   (default: verify-l3.sh's own, the TactiQ AI root r2)
#   VERIFY_EK_ROOT, VERIFY_EK_INTERMEDIATE, VERIFY_EK_ROOT_FP, VERIFY_TPM_FW_MIN
#                   passed to verify-l3.sh as --ek-root, --ek-intermediate,
#                   --ek-root-fp, --tpm-fw-min when set
#   ALLOW_NO_L3=1   write SHA256SUMS without the L3 files and checks. For
#                   mechanics testing ONLY; the output is NOT a valid release.
set -euo pipefail
[[ $# -eq 2 ]] || { echo "usage: $0 <release-tag> <output-dir>" >&2; exit 2; }
TAG="$1"; OUT="$(cd "$2" && pwd)"
SHORT="${TAG##*-}"
ARCH="l3-evidence-${SHORT}.tar.gz"; PAGE="VERIFY-L3-${SHORT}.md"; SCRIPT="verify-l3.sh"
BOARD="${BOARD:-rock5a}"
ROOT_FILE="${VERIFY_ROOT_FILE:-release-root-r2.pem}"
SRC_SCRIPT="$(cd "$(dirname "$0")" && pwd)/verify-l3.sh"
EV_EKU="2.25.303991386130890852620485224389791976682"
cd "$OUT"
[[ -e SHA256SUMS ]] && { echo "::error:: $OUT/SHA256SUMS exists; this script writes it once." >&2; exit 1; }

l3=1
if [[ "${ALLOW_NO_L3:-0}" == 1 ]]; then
    l3=0; echo "::warning:: ALLOW_NO_L3=1: no L3 evidence checks. The output is NOT a valid release."
else
    # The script that checks the release is the one in this tree. A copy
    # already in <dir> must be that same file, so a stale one cannot be signed.
    if [[ -e "$SCRIPT" ]]; then
        cmp -s "$SCRIPT" "$SRC_SCRIPT" || { echo "::error:: $OUT/$SCRIPT differs from $SRC_SCRIPT" >&2; exit 1; }
    else
        cp -- "$SRC_SCRIPT" "$SCRIPT"
    fi
    for f in "$ARCH" "$PAGE" "$SCRIPT" "rim-${BOARD}.json" "rim-${BOARD}.json.p7s"; do [[ -r "$f" ]] || { echo "::error:: $f missing in $OUT" >&2; exit 1; }; done
    [[ -n "${VERIFY_ROOT_CA:-}" && -r "$VERIFY_ROOT_CA" ]] || { echo "::error:: VERIFY_ROOT_CA is not set, or is unreadable." >&2; exit 1; }
    W="$(mktemp -d)"; trap 'rm -rf "$W"' EXIT
    tar -xzf "$ARCH" -C "$W"
    E="$W/l3-evidence-${SHORT}"
    [[ -d "$E" ]] || { echo "::error:: $ARCH does not unpack to l3-evidence-${SHORT}/" >&2; exit 1; }
    ( cd "$E" && sha256sum --check --strict --quiet SHA256SUMS ) || { echo "::error:: $ARCH: its SHA256SUMS does not match its files" >&2; exit 1; }
    openssl cms -verify -binary -inform DER -in "$E/SHA256SUMS.p7s" -content "$E/SHA256SUMS" \
        -CAfile "$VERIFY_ROOT_CA" -certfile "$E/signing-ca.pem" -purpose any -signer "$W/ev.pem" -out /dev/null 2>/dev/null \
        || { echo "::error:: $ARCH: SHA256SUMS.p7s does not verify to VERIFY_ROOT_CA" >&2; exit 1; }
    openssl x509 -in "$W/ev.pem" -noout -ext extendedKeyUsage | grep -qx "[[:space:]]*${EV_EKU}" \
        || { echo "::error:: $ARCH: the evidence list is not signed by an Evidence Signer leaf" >&2; exit 1; }
    echo "    = $ARCH: list verifies to the release root, Evidence Signer purpose"
fi

echo "==> SHA256SUMS"
shopt -s nullglob; files=( * ); shopt -u nullglob
[[ ${#files[@]} -gt 0 ]] || { echo "::error:: no artifacts to hash" >&2; exit 1; }
# Copies inherit the mode of their source, which on some hosts is 0777.
# Normalise: data 0644, scripts 0755.
chmod 0644 -- "${files[@]}"
for s in mk-pcr-reference.py "$SCRIPT"; do [[ -e "$s" ]] && chmod 0755 -- "$s"; done
sha256sum -- "${files[@]}" | LC_ALL=C sort -k2 > SHA256SUMS

if [[ "$l3" == 1 ]]; then
    echo "==> $SCRIPT on $OUT (tag $TAG, board $BOARD)"
    R="$W/run"; mkdir "$R"
    cp -- "$VERIFY_ROOT_CA" "$R/$ROOT_FILE"
    cp -- "rim-${BOARD}.json" "rim-${BOARD}.json.p7s" "$R/"
    cp -- SHA256SUMS "$ARCH" "$R/"
    args=(--tag "$TAG" --board "$BOARD" --root-file "$ROOT_FILE")
    [[ -n "${VERIFY_ROOT_FP:-}" ]]         && args+=(--root-fp "$VERIFY_ROOT_FP")
    [[ -n "${VERIFY_EK_ROOT:-}" ]]         && args+=(--ek-root "$VERIFY_EK_ROOT")
    [[ -n "${VERIFY_EK_INTERMEDIATE:-}" ]] && args+=(--ek-intermediate "$VERIFY_EK_INTERMEDIATE")
    [[ -n "${VERIFY_EK_ROOT_FP:-}" ]]      && args+=(--ek-root-fp "$VERIFY_EK_ROOT_FP")
    [[ -n "${VERIFY_TPM_FW_MIN:-}" ]]      && args+=(--tpm-fw-min "$VERIFY_TPM_FW_MIN")
    if bash "$OUT/$SCRIPT" "${args[@]}" --dir "$R" > "$W/l3.txt" 2>&1; then
        tail -n 2 "$W/l3.txt"
    else
        cat "$W/l3.txt"; rm -f SHA256SUMS
        echo "::error:: $SCRIPT did not exit 0 on the assembled release; SHA256SUMS removed." >&2
        exit 1
    fi
fi
echo "==> done: ${OUT}  (tag ${TAG})"
