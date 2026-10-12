#!/usr/bin/env bash
# resign-bundle.sh: replace the development signature of a RAUC bundle with
# the release signature, offline, and prove the result.
#
# Usage: resign-bundle.sh <bundle-in.raucb> <bundle-out.raucb>
#
# The release build signs tactiq-bundle with the development signer, because
# bitbake cannot answer the passphrase prompt of the release key
# (conf/bundle-devsign.conf). This script is the step that turns that bundle
# into a release bundle (RELEASE_INTEGRITY.md §2.3: bundles are re-signed
# offline with `rauc resign`).
#
# rauc needs the image's system.conf for the [keyring] check-purpose; without
# it the release signer is refused with "unsuitable certificate purpose". The
# image's system.conf also names device paths (data-directory=/var/lib/rauc),
# which rauc tries to create on the host. The script therefore runs rauc with
# a copy of that file in which data-directory points into a temporary
# directory, and checks that this is the only line that differs. The file in
# the image is not touched.
#
# After signing, the result must verify against the release root, and must
# NOT verify against the development root in pki/dev/. The release root is
# accepted only if its SHA-256 fingerprint equals the pinned r2 fingerprint.
# On any failure the output file is removed.
#
# Environment:
#   RAUC         the rauc binary of the build (tactiq-bundle recipe-sysroot-native)
#   SYSTEM_CONF  the system.conf installed in the image (rauc-conf image/etc/rauc)
#   KEY_DIR      the release key directory (default /mnt/k/release): root-ca.pem,
#                signing-ca.pem, signer.pem, signer.key.pem
set -euo pipefail
[[ $# -eq 2 ]] || { echo "usage: $0 <bundle-in.raucb> <bundle-out.raucb>" >&2; exit 2; }
IN="$1"; OUT="$2"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEV_ROOT="${SCRIPT_DIR}/../pki/dev/root-ca.pem"
KEY_DIR="${KEY_DIR:-/mnt/k/release}"
R2_ROOT_FP="8E:10:04:1E:BB:FC:CB:A0:36:62:1B:2E:45:36:87:D2:9A:50:D7:15:65:F2:99:CB:41:28:B4:CE:B9:65:FF:E8"

die() { echo "::error:: $*" >&2; exit 1; }
for v in RAUC SYSTEM_CONF; do
    [[ -n "${!v:-}" && -r "${!v}" ]] || die "${v} is not set, or is unreadable."
done
[[ -x "$RAUC" ]] || die "RAUC ($RAUC) is not executable."
for f in "$IN" "$DEV_ROOT" "$KEY_DIR/root-ca.pem" "$KEY_DIR/signing-ca.pem" "$KEY_DIR/signer.pem" "$KEY_DIR/signer.key.pem"; do
    [[ -r "$f" ]] || die "$f is missing or unreadable."
done
[[ -e "$OUT" ]] && die "$OUT exists; refusing to overwrite."

fp="$(openssl x509 -in "$KEY_DIR/root-ca.pem" -noout -fingerprint -sha256 | sed 's/^[^=]*=//')"
[[ "$fp" == "$R2_ROOT_FP" ]] || die "$KEY_DIR/root-ca.pem is not the r2 release root (fingerprint $fp)."
grep -q '^check-purpose=' "$SYSTEM_CONF" || die "$SYSTEM_CONF has no check-purpose; it is not the image's system.conf."

W="$(mktemp -d)"
cleanup() { rm -rf "$W"; }
trap cleanup EXIT
mkdir "$W/data"
HOSTCONF="$W/system.conf"
sed "s|^data-directory=.*$|data-directory=$W/data|" "$SYSTEM_CONF" > "$HOSTCONF"
changed="$(diff "$SYSTEM_CONF" "$HOSTCONF" | grep -c '^>' || true)"
[[ "$changed" -le 1 ]] || die "host copy of system.conf differs in $changed lines, expected at most 1."

fail() { rm -f -- "$OUT"; die "$*"; }

echo "==> resign $(basename "$IN") -> $OUT"
"$RAUC" -c "$HOSTCONF" resign --no-verify \
    --cert="$KEY_DIR/signer.pem" --key="$KEY_DIR/signer.key.pem" \
    --intermediate="$KEY_DIR/signing-ca.pem" --signing-keyring="$KEY_DIR/root-ca.pem" \
    "$IN" "$OUT" || fail "rauc resign failed."

echo "==> verify against the release root"
"$RAUC" -c "$HOSTCONF" info --keyring="$KEY_DIR/root-ca.pem" "$OUT" > "$W/info.txt" 2>&1 \
    || { cat "$W/info.txt" >&2; fail "the re-signed bundle does not verify against the release root."; }
grep -i -E 'signer|verified' "$W/info.txt" || true

echo "==> verify against the development root (must fail)"
if "$RAUC" -c "$HOSTCONF" info --keyring="$DEV_ROOT" "$OUT" > "$W/dev.txt" 2>&1; then
    fail "the re-signed bundle verifies against the development root in pki/dev/."
fi
echo "    refused, as required"

echo "==> done: $OUT  sha256 $(sha256sum "$OUT" | cut -d' ' -f1)"
