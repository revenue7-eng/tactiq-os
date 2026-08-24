#!/usr/bin/env bash
#
# verify-ek-chain.sh — verify a TPM Endorsement Key certificate against the
# manufacturer's CA chain.
#
# The EK certificate binds a TPM's endorsement key to a manufacturer-issued
# identity. Verifying its chain is what distinguishes "a TPM answered" from
# "this specific TPM, issued by this manufacturer, answered".
#
# The procedure is executed by the operator. Nothing in this repository is
# evidence that it succeeded on any particular device: run it and read the
# exit status.
#
# Two stages, separable:
#
#   1. Extraction — read the certificate out of TPM NV storage. Requires the
#      device. Produces a DER file.
#   2. Verification — build the chain and check it. Requires network access to
#      the manufacturer PKI and a host with correct wall-clock time.
#
# Devices without an RTC report a fabricated time, under which certificate
# validity cannot be judged. Run stage 2 on a host whose clock is correct.
#
# Usage:
#   verify-ek-chain.sh [-e ek.der] [-i ca.crt] [-r root.crt]
#                      [-o outdir] [-n index] [-k]
#
#   -e FILE   EK certificate in DER form. Default: read from the local TPM.
#   -i FILE   Intermediate CA certificate. Default: fetch over the network
#             using the CA Issuers URI carried in the EK certificate.
#   -r FILE   Trusted root certificate, obtained out of band. Recommended.
#             Without it the root is fetched over the network and the result
#             is reported as UNPINNED (see below).
#   -o DIR    Output directory. Default: ./ek-chain-evidence
#   -n INDEX  NV index holding the EK certificate. Default: 0x01C00002 (RSA).
#             Use 0x01C0000A for the ECC certificate.
#   -k        Permit an unpinned root. Without this flag, a missing -r is a
#             hard failure.
#
# With -e, -i and -r supplied the script makes no network request at all, and
# runs on a host with no route to the manufacturer PKI. The certificates have
# to reach that host somehow; how they got there is the operator's business,
# and the SHA-256 values printed at the end are what tie them to their source.
#
# On the unpinned root: a self-signed root fetched over the same network as
# everything else anchors nothing. An adversary able to serve a substituted
# root can serve a chain that validates against it. Supply -r with a root
# obtained independently, and compare the SHA-256 this script prints against
# the value the manufacturer publishes.
#
# Exit status: 0 only if the chain verifies. Any other value means the chain
# was not established, for whatever reason.

set -euo pipefail

NV_INDEX="0x01C00002"
OUT_DIR="ek-chain-evidence"
EK_FILE=""
INT_FILE=""
ROOT_FILE=""
ALLOW_UNPINNED=0
CURL_TIMEOUT=30

die() {
	printf 'error: %s\n' "$*" >&2
	exit 1
}

note() {
	printf '%s\n' "$*" >&2
}

usage() {
	sed -n '3,56p' "$0" | sed 's/^# \{0,1\}//'
	exit 2
}

while getopts ':e:i:r:o:n:kh' opt; do
	case "$opt" in
	e) EK_FILE="$OPTARG" ;;
	i) INT_FILE="$OPTARG" ;;
	r) ROOT_FILE="$OPTARG" ;;
	o) OUT_DIR="$OPTARG" ;;
	n) NV_INDEX="$OPTARG" ;;
	k) ALLOW_UNPINNED=1 ;;
	h) usage ;;
	:) die "option -$OPTARG requires an argument" ;;
	?) die "unknown option -$OPTARG" ;;
	esac
done

command -v openssl >/dev/null 2>&1 || die "openssl not found"

if [ -z "$ROOT_FILE" ] && [ "$ALLOW_UNPINNED" -eq 0 ]; then
	die "no trusted root supplied; pass -r FILE, or -k to accept a network-fetched root"
fi

mkdir -p "$OUT_DIR"

# --- stage 1: obtain the EK certificate ------------------------------------

if [ -n "$EK_FILE" ]; then
	[ -r "$EK_FILE" ] || die "cannot read $EK_FILE"
	cp -- "$EK_FILE" "$OUT_DIR/ek.der"
else
	command -v tpm2_nvreadpublic >/dev/null 2>&1 ||
		die "tpm2-tools not found and no -e FILE given"

	note "reading EK certificate from NV $NV_INDEX"

	# The NV read needs an explicit size; take it from the public area rather
	# than assuming one. A short read yields a truncated DER that fails to
	# parse, which is a confusing way to learn the size was wrong.
	nv_size="$(tpm2_nvreadpublic "$NV_INDEX" |
		awk '/^[[:space:]]*size:/ { print $2; exit }')"

	[ -n "$nv_size" ] || die "no NV index $NV_INDEX on this TPM"

	tpm2_nvread -C o "$NV_INDEX" -s "$nv_size" -o "$OUT_DIR/ek.der" ||
		die "NV read failed"
fi

openssl x509 -inform DER -in "$OUT_DIR/ek.der" -noout >/dev/null 2>&1 ||
	die "$OUT_DIR/ek.der is not a DER certificate"

# --- stage 2: build the chain ----------------------------------------------

# Follow the CA Issuers URI carried in the certificate itself rather than
# hardcoding a manufacturer URL: the intermediate differs per production lot,
# and a stale hardcoded path fails in a way that looks like a bad certificate.
aia_uri() {
	openssl x509 -inform DER -in "$1" -noout -text |
		awk '/CA Issuers - URI:/ { sub(/.*URI:/, ""); print; exit }'
}

fetch() {
	command -v curl >/dev/null 2>&1 || die "curl not found; fetch $1 manually"
	curl -fsS -m "$CURL_TIMEOUT" -o "$2" -- "$1" || die "fetch failed: $1"
}

if [ -n "$INT_FILE" ]; then
	[ -r "$INT_FILE" ] || die "cannot read $INT_FILE"
	cp -- "$INT_FILE" "$OUT_DIR/intermediate.crt"
	int_origin="supplied out of band: $INT_FILE"

	# An intermediate handed in on the command line is not assumed to be the
	# right one: check it actually names the issuer the EK certificate points
	# at. Otherwise a wrong-lot CA fails later as an opaque verify error.
	want_cn="$(openssl x509 -inform DER -in "$OUT_DIR/ek.der" -noout -issuer)"
	have_cn="$(openssl x509 -inform DER -in "$OUT_DIR/intermediate.crt" \
		-noout -subject 2>/dev/null | sed 's/^subject=/issuer=/')"
	[ "$want_cn" = "$have_cn" ] ||
		die "intermediate does not match EK issuer: $want_cn vs $have_cn"
else
	int_uri="$(aia_uri "$OUT_DIR/ek.der")"
	[ -n "$int_uri" ] || die "EK certificate carries no CA Issuers URI"
	note "fetching intermediate: $int_uri"
	fetch "$int_uri" "$OUT_DIR/intermediate.crt"
	int_origin="fetched from $int_uri"
fi

if [ -n "$ROOT_FILE" ]; then
	[ -r "$ROOT_FILE" ] || die "cannot read $ROOT_FILE"
	cp -- "$ROOT_FILE" "$OUT_DIR/root.crt"
	root_origin="supplied out of band: $ROOT_FILE"
else
	root_uri="$(aia_uri "$OUT_DIR/intermediate.crt")"
	[ -n "$root_uri" ] || die "intermediate carries no CA Issuers URI"
	note "fetching root: $root_uri"
	note "WARNING: root fetched over the network, not independently pinned"
	fetch "$root_uri" "$OUT_DIR/root.crt"
	root_origin="UNPINNED, fetched from $root_uri"
fi

for f in ek intermediate root; do
	openssl x509 -inform DER -in "$OUT_DIR/$f.crt" -out "$OUT_DIR/$f.pem" 2>/dev/null ||
		openssl x509 -inform DER -in "$OUT_DIR/$f.der" -out "$OUT_DIR/$f.pem" 2>/dev/null ||
		die "cannot convert $f to PEM"
done

# --- verify -----------------------------------------------------------------

verify_out="$(openssl verify \
	-CAfile "$OUT_DIR/root.pem" \
	-untrusted "$OUT_DIR/intermediate.pem" \
	"$OUT_DIR/ek.pem" 2>&1)" && verify_rc=0 || verify_rc=$?

# --- record ------------------------------------------------------------------

(
	cd "$OUT_DIR" && sha256sum ek.der intermediate.crt root.crt >SHA256SUMS
)

{
	printf 'host=%s\n' "$(uname -n)"
	printf 'date_utc=%s\n' "$(date -u +%FT%TZ)"
	printf 'openssl=%s\n' "$(openssl version)"
	printf 'nv_index=%s\n' "$NV_INDEX"
	printf 'intermediate_origin=%s\n' "$int_origin"
	printf 'root_origin=%s\n' "$root_origin"
	printf 'ek_issuer=%s\n' \
		"$(openssl x509 -in "$OUT_DIR/ek.pem" -noout -issuer | sed 's/^issuer=//')"
	printf 'ek_validity=%s\n' \
		"$(openssl x509 -in "$OUT_DIR/ek.pem" -noout -dates | tr '\n' ' ')"
	printf 'verify_rc=%s\n' "$verify_rc"
	printf 'verify_out=%s\n' "$verify_out"
} >"$OUT_DIR/verification.txt"

cat "$OUT_DIR/SHA256SUMS"
cat "$OUT_DIR/verification.txt"

if [ "$verify_rc" -ne 0 ]; then
	die "chain NOT established"
fi

if [ "$ALLOW_UNPINNED" -eq 1 ] && [ -z "$ROOT_FILE" ]; then
	note "chain verified against an UNPINNED root; compare root.crt against the"
	note "manufacturer's published fingerprint before relying on this result"
fi

note "chain established"
