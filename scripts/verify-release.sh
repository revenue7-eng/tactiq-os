#!/usr/bin/env bash
# verify-release.sh — independently verify a tactiq-os release without
# trusting the build machine. Each step prints exactly what it proves; the
# script makes no claim it cannot back from the published artifacts.
#
# Verification chain:
#   1. The cosign signature over SHA256SUMS is valid and the signing identity
#      is the expected release-sign.yml workflow (GitHub OIDC). This
#      authenticates SHA256SUMS itself — the trust root is the publicly
#      reviewable workflow, not a personal account or the build machine.
#   2. Every artifact's SHA-256 matches SHA256SUMS. Because step 1
#      authenticated SHA256SUMS, this authenticates the whole artifact set.
#   3. The SBOM is a valid SPDX 3.0.1 document with content and is part of the
#      signed set (release-level binding of the SBOM to the image). Byte-level
#      proof that the SBOM enumerates this exact image is NOT claimed here —
#      that is what reproducibility provides.
#   4. The CVE report is present and parses. (Posture gating — no unjustified
#      critical/high — is a separate step, not done here.)
#
# Usage:
#   verify-release.sh --tag <tag> [--repo owner/repo]   # fetch assets via gh
#   verify-release.sh --dir <dir> [--identity <id>]     # verify local assets
#
# Options:
#   --repo owner/repo   default revenue7-eng/tactiq-os
#   --board <name>      default rock5a
#   --identity <id>     override the expected cosign certificate-identity
#                       (e.g. the personal-identity signature, or a local
#                       --dir check where the tag cannot be derived)
#   --allow-unsigned    skip the signature step. DEV/TESTING ONLY — the result
#                       then authenticates nothing.
#
# Requires: cosign, jq, sha256sum; gh only for --tag.

set -euo pipefail

REPO="revenue7-eng/tactiq-os"
BOARD="rock5a"
ISSUER="https://token.actions.githubusercontent.com"
TAG="" DIR="" IDENTITY="" ALLOW_UNSIGNED=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --tag) TAG="$2"; shift 2 ;;
        --dir) DIR="$2"; shift 2 ;;
        --repo) REPO="$2"; shift 2 ;;
        --board) BOARD="$2"; shift 2 ;;
        --identity) IDENTITY="$2"; shift 2 ;;
        --allow-unsigned) ALLOW_UNSIGNED=1; shift ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
done

if [[ -z "$TAG" && -z "$DIR" ]]; then
    echo "usage: $0 --tag <tag> [--repo owner/repo] | --dir <dir>" >&2
    exit 2
fi

pass=0 fail=0 authd=1
ok()   { echo "  [PASS] $*"; pass=$((pass + 1)); }
bad()  { echo "  [FAIL] $*" >&2; fail=$((fail + 1)); }
need() { command -v "$1" >/dev/null 2>&1 || { echo "::error:: required tool not found: $1" >&2; exit 1; }; }

need jq; need sha256sum

# ---------------------------------------------------------------------------
# Resolve the asset directory.
# ---------------------------------------------------------------------------
CLEANUP=""
if [[ -n "$TAG" ]]; then
    need gh
    DIR="$(mktemp -d)"; CLEANUP="$DIR"
    echo "==> downloading release ${TAG} from ${REPO}"
    gh release download "$TAG" --repo "$REPO" --dir "$DIR"
fi
[[ -d "$DIR" ]] || { echo "::error:: asset dir not found: $DIR" >&2; exit 1; }
cd "$DIR"
# shellcheck disable=SC2064
[[ -n "$CLEANUP" ]] && trap "rm -rf '$CLEANUP'" EXIT

echo "==> verifying release in: $DIR"
[[ -f SHA256SUMS ]] || { echo "::error:: SHA256SUMS not found in asset set" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Step 1 — signature over SHA256SUMS.
# ---------------------------------------------------------------------------
echo "-- step 1: signature over SHA256SUMS"
if [[ "$ALLOW_UNSIGNED" == 1 ]]; then
    echo "  [SKIP] --allow-unsigned set — signature NOT checked (authenticates nothing)"
    authd=0
elif [[ -f SHA256SUMS.workflow.pem && -f SHA256SUMS.workflow.sig ]]; then
    need cosign
    id="$IDENTITY"
    if [[ -z "$id" ]]; then
        [[ -n "$TAG" ]] || { echo "::error:: workflow signature present but no --tag to derive identity; pass --identity" >&2; exit 1; }
        id="https://github.com/${REPO}/.github/workflows/release-sign.yml@refs/tags/${TAG}"
    fi
    if cosign verify-blob \
            --certificate SHA256SUMS.workflow.pem \
            --signature   SHA256SUMS.workflow.sig \
            --certificate-identity        "$id" \
            --certificate-oidc-issuer     "$ISSUER" \
            SHA256SUMS >/dev/null 2>&1; then
        ok "cosign workflow-identity signature valid ($id)"
    else
        bad "cosign workflow-identity signature did NOT verify against $id"
    fi
elif [[ -f SHA256SUMS.pem && -f SHA256SUMS.sig ]]; then
    need cosign
    if [[ -z "$IDENTITY" ]]; then
        bad "personal-identity signature present but no --identity given to verify against"
    elif cosign verify-blob \
            --certificate SHA256SUMS.pem --signature SHA256SUMS.sig \
            --certificate-identity "$IDENTITY" \
            --certificate-oidc-issuer "https://github.com/login/oauth" \
            SHA256SUMS >/dev/null 2>&1; then
        ok "cosign personal-identity signature valid ($IDENTITY)"
    else
        bad "cosign personal-identity signature did NOT verify against $IDENTITY"
    fi
else
    bad "no signature assets found (SHA256SUMS.workflow.{pem,sig} or SHA256SUMS.{pem,sig})"
fi

# ---------------------------------------------------------------------------
# Step 2 — artifact hashes.
# ---------------------------------------------------------------------------
echo "-- step 2: artifact hashes vs SHA256SUMS"
if sha256sum -c SHA256SUMS >/dev/null 2>&1; then
    ok "all $(grep -c . SHA256SUMS) listed artifacts match their SHA-256"
else
    bad "one or more artifacts failed sha256sum -c (see: sha256sum -c SHA256SUMS)"
fi

# ---------------------------------------------------------------------------
# Step 3 — SBOM validity + membership in the signed set.
# ---------------------------------------------------------------------------
echo "-- step 3: SBOM (SPDX 3.0.1) validity and binding"
SBOM="sbom-${BOARD}.spdx.json"
if [[ ! -f "$SBOM" ]]; then
    bad "SBOM not found: $SBOM"
else
    if grep -q " ${SBOM}\$" SHA256SUMS; then
        ok "SBOM is listed in the signed SHA256SUMS"
    else
        bad "SBOM present on disk but NOT listed in SHA256SUMS (unsigned)"
    fi
    ver="$(jq -r '.. | objects | select(has("specVersion")) | .specVersion' "$SBOM" 2>/dev/null | sort -u | head -1)"
    if [[ "$ver" == "3.0.1" ]]; then ok "SBOM specVersion is 3.0.1"; else bad "SBOM specVersion is '${ver:-<none>}', expected 3.0.1"; fi
    npkg="$(jq -r '[(.["@graph"]//.)[]?|select(.type=="software_Package")]|length' "$SBOM" 2>/dev/null || echo 0)"
    nfile="$(jq -r '[(.["@graph"]//.)[]?|select(.type=="software_File")]|length' "$SBOM" 2>/dev/null || echo 0)"
    nsbom="$(jq -r '[(.["@graph"]//.)[]?|select(.type=="software_Sbom")]|length' "$SBOM" 2>/dev/null || echo 0)"
    if [[ "$nsbom" -ge 1 && "$npkg" -gt 0 && "$nfile" -gt 0 ]]; then
        ok "SBOM is self-contained (software_Sbom=$nsbom, packages=$npkg, files=$nfile)"
    else
        bad "SBOM structure incomplete (software_Sbom=$nsbom, packages=$npkg, files=$nfile)"
    fi
fi

# Image membership — the deliverable must be in the signed set.
IMG="image-${BOARD}.wic.gz"
if grep -q " ${IMG}\$" SHA256SUMS; then
    ok "image ${IMG} is in the signed set"
else
    bad "image ${IMG} not listed in SHA256SUMS"
fi

# ---------------------------------------------------------------------------
# Step 4 — CVE report present and parseable.
# ---------------------------------------------------------------------------
echo "-- step 4: CVE report"
CVE="cve-${BOARD}.sbom-cve-check.yocto.json"
if [[ -f "$CVE" ]] && jq -e '.package' "$CVE" >/dev/null 2>&1; then
    ok "CVE report present and parses ($(jq '.package|length' "$CVE") packages with CVE data)"
else
    bad "CVE report missing or unparseable: $CVE"
fi

# ---------------------------------------------------------------------------
# Summary.
# ---------------------------------------------------------------------------
echo "==> result: ${pass} passed, ${fail} failed"
[[ "$fail" -eq 0 ]] || exit 1
if [[ "$authd" == 1 ]]; then
    echo "==> RELEASE VERIFIED"
else
    echo "==> checks passed, but the signature was NOT verified — release is NOT authenticated"
fi
