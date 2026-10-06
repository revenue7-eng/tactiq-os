#!/usr/bin/env bash
# mk-l3-evidence.sh: pack the L3 evidence of a release and sign its list of
# files under the release hierarchy.
#
# Usage: mk-l3-evidence.sh <release-tag> <evidence-dir> <output-dir>
#
# <evidence-dir> holds the files taken from the reference device running the
# release (envelopes NNN.msg, .attest, .sig; ak.pub; ek.der; the registration
# record and its .p7s; reg-signer.pem; signing-ca.pem; the two Infineon
# certificates). Nothing else may be in it: every file goes into the list.
#
# The script writes SHA256SUMS over those files, signs it with the Evidence
# Signer (CMS detached, SHA256SUMS.p7s), checks the signature against the
# release root, and packs <output-dir>/l3-evidence-<rcN>.tar.gz with one
# top-level directory l3-evidence-<rcN>/. Run it offline, where the key is.
#
# Environment (all required):
#   EVIDENCE_SIGNER_CERT  the Evidence Signer leaf (gen-pki.sh evsigner-prod)
#   EVIDENCE_SIGNER_KEY   its key; openssl asks for the passphrase
#   EVIDENCE_SIGNING_CA   the Signing CA that issued the leaf
#   EVIDENCE_ROOT_CA      the release root
#
# The archive must exist before scripts/mk-release-sums.sh writes the
# release's SHA256SUMS, so that the Sigstore signature covers it too.
set -euo pipefail
[[ $# -eq 3 ]] || { echo "usage: $0 <release-tag> <evidence-dir> <output-dir>" >&2; exit 2; }
TAG="$1"; EVD="$(cd "$2" && pwd)"; OUT="$(cd "$3" && pwd)"
SHORT="${TAG##*-}"
NAME="l3-evidence-${SHORT}"
EV_EKU="2.25.303991386130890852620485224389791976682"
for v in EVIDENCE_SIGNER_CERT EVIDENCE_SIGNER_KEY EVIDENCE_SIGNING_CA EVIDENCE_ROOT_CA; do
    [[ -n "${!v:-}" && -r "${!v}" ]] || { echo "::error:: ${v} is not set, or is unreadable." >&2; exit 1; }
done
if ! openssl x509 -in "$EVIDENCE_SIGNER_CERT" -noout -ext extendedKeyUsage 2>/dev/null | grep -qx "[[:space:]]*${EV_EKU}"; then
    echo "::error:: ${EVIDENCE_SIGNER_CERT} is not an Evidence Signer leaf: its only EKU must be ${EV_EKU}." >&2
    exit 1
fi
openssl verify -CAfile "$EVIDENCE_ROOT_CA" -untrusted "$EVIDENCE_SIGNING_CA" "$EVIDENCE_SIGNER_CERT" >/dev/null \
    || { echo "::error:: ${EVIDENCE_SIGNER_CERT} does not chain to EVIDENCE_ROOT_CA through EVIDENCE_SIGNING_CA." >&2; exit 1; }
[[ -e "$OUT/$NAME.tar.gz" ]] && { echo "::error:: $OUT/$NAME.tar.gz exists; refusing to overwrite evidence." >&2; exit 1; }

W="$(mktemp -d)"; trap 'rm -rf "$W"' EXIT
mkdir "$W/$NAME"
cp -p -- "$EVD"/* "$W/$NAME"/
cd "$W/$NAME"
rm -f SHA256SUMS SHA256SUMS.p7s
ls *.attest >/dev/null 2>&1 || { echo "::error:: no quote (*.attest) in $EVD" >&2; exit 1; }
[[ $(ls registration-*.json 2>/dev/null | wc -l) -eq 1 ]] || { echo "::error:: $EVD must hold exactly one registration-*.json" >&2; exit 1; }
chmod 0644 -- *
LC_ALL=C sha256sum -- $(LC_ALL=C ls) > SHA256SUMS
openssl cms -sign -binary -noattr -md sha256 \
    -in SHA256SUMS -signer "$EVIDENCE_SIGNER_CERT" -inkey "$EVIDENCE_SIGNER_KEY" \
    -certfile "$EVIDENCE_SIGNING_CA" -outform DER -out SHA256SUMS.p7s
openssl cms -verify -binary -inform DER -in SHA256SUMS.p7s -content SHA256SUMS \
    -CAfile "$EVIDENCE_ROOT_CA" -purpose any -out /dev/null 2>/dev/null \
    || { echo "::error:: SHA256SUMS.p7s does not verify to EVIDENCE_ROOT_CA." >&2; exit 1; }
chmod 0644 SHA256SUMS SHA256SUMS.p7s
cd "$W"
tar --sort=name --owner=0 --group=0 --numeric-owner -czf "$OUT/$NAME.tar.gz" "$NAME"
echo "    + $NAME.tar.gz  $(sha256sum "$OUT/$NAME.tar.gz" | cut -d' ' -f1)"
echo "      $(wc -l < "$NAME/SHA256SUMS") files, list signed by $(openssl x509 -in "$EVIDENCE_SIGNER_CERT" -noout -subject -nameopt RFC2253 | sed 's/^subject=//')"
