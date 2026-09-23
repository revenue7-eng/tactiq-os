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
#   BOOT_ENV             default: the tactiq-boot.env of the rockchip BSP layer
#   SKIP_BUILDINFO=1     skip the bitbake -e buildinfo capture (no build env)
#   BUILDINFO_CONF       extra config file passed to bitbake -e as -R, the same
#                        file the image was built with (release keys). Required
#                        when the FIT is not signed with dev-fit, so buildinfo
#                        describes the configuration that produced the release
#   ALLOW_MIXED_BUILD=1  downgrade the single-build guard to a warning. For dev
#                        mechanics testing ONLY — the output is NOT a valid
#                        release (manifest / SBOM / image may be from different
#                        builds).
#   ALLOW_DEV_FIT_KEY=1  let IMAGE=tactiq-image ship a FIT signed with the
#                        development key. The output is NOT a valid release.
#   ALLOW_IDENTITY_MISMATCH=1  let the release proceed when /etc/tactiq-release
#                        in the image does not name the tag. For mechanics
#                        testing ONLY; the output is NOT a valid release.
#   ALLOW_KNOWN_ISSUES_GAP=1  let the release proceed when an issue the
#                        previous release left open is missing from this
#                        manifest. For mechanics testing ONLY; the output
#                        is NOT a valid release.
#   ALLOW_BUILD_ID_MISMATCH=1  let the release proceed when manifest.build_id
#                        of the tagged coverage manifest does not name the
#                        build in the deploy tree. For mechanics testing
#                        ONLY; the output is NOT a valid release.
#   RIM_SIGNER_CERT, RIM_SIGNER_KEY, RIM_SIGNING_CA, RIM_ROOT_CA
#                        the RIM leaf, its key, the Signing CA and the release
#                        root; see the RIM block below. Without them the RIM
#                        is left unsigned.
#   ALLOW_NO_RIM=1       let IMAGE=tactiq-image go without a signed RIM or
#                        without security/rim-disclosures-<board>.txt. For
#                        mechanics testing ONLY; the output is NOT a valid
#                        release.
#
# Produces in <output-dir>:
#   image-${BOARD}.wic.gz, image-${BOARD}.wic.bmap   (compressed image + bmap;
#       the raw .wic is ~9.8 GB and exceeds the GitHub 2 GB asset limit, so we
#       publish the .gz + .bmap — flash with: bmaptool copy image.wic.gz /dev/sdX)
#   kernel-${BOARD}.bin, rk3588s-rock-5a.dtb
#   fitImage-${BOARD}, extlinux-${BOARD}.conf        (as found on the boot partition)
#   idbloader-${BOARD}.img, u-boot-${BOARD}.itb      (SPL, the root of the measurement
#       chain, and the images it measures)
#   tactiq-boot-${BOARD}.env                         (U-Boot default environment)
#   pcr-reference-${BOARD}.json, mk-pcr-reference.py (expected boot PCRs and the
#       script that recomputes them from the four files above)
#   manifest-${BOARD}.txt, testdata-${BOARD}.json, buildinfo-${BOARD}.json
#   sbom-${BOARD}.spdx.json                          (SPDX 3.0.1)
#   cve-${BOARD}.sbom-cve-check.yocto.json
#   bundle-${BOARD}.raucb                            (required for IMAGE=tactiq-image)
#   tactiq-release-${BOARD}                          (/etc/tactiq-release from the release rootfs)
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
BOOT_ENV="${BOOT_ENV:-${SCRIPT_DIR}/../meta-tactiq-bsp-rockchip/recipes-bsp/u-boot/files/tactiq-boot.env}"

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
# (Kernel and DTB have a separate deploy lifecycle and are taken as-is; the
# PCR reference step below checks both against the FIT on the boot partition.)
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

ROOTFS_ARTIFACTS=( wic.gz wic.bmap bootext4 ext4 spdx.json sbom-cve-check.yocto.json manifest testdata.json )
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

# ---------------------------------------------------------------------------
# Release-identity gate.
#
# The guard above proves the deploy dir is internally consistent: all rootfs
# artifacts from ONE build. It cannot prove it is THE build this tag ships. A
# stale but self-consistent deploy tree passes it silently, and everything
# below this line overwrites the artifact set. The coverage manifest is the
# only file in this pipeline that is committed, pinned to the tag and covered
# by the release signature, so it is the external statement the tree is
# checked against.
#
# If build_id here is wrong, the tag is wrong: the manifest is pinned to the
# tag, so the remedy is a new tag, not an edit to a published manifest.
# ---------------------------------------------------------------------------
COV_SRC="${SCRIPT_DIR}/../security/coverage-${BOARD}.${TAG}.yaml"
[[ -e "$COV_SRC" ]] || { echo "::error:: coverage manifest not found: $COV_SRC" >&2; exit 1; }

cov_field() {  # echo a 2-space-indented scalar from the top-level manifest: block
    awk -v k="$1" '
        /^manifest:[ \t]*$/ { m = 1; next }
        /^[^ \t#]/          { m = 0 }
        m && $0 ~ "^  " k ":" {
            sub("^  " k ":[ \t]*", "")
            sub("[ \t]*(#.*)?$", "")
            gsub(/^"|"$/, "")
            print; exit
        }
    ' "$COV_SRC"
}

COV_BUILD_ID="$(cov_field build_id)"
COV_GENERATED="$(cov_field generated_utc)"

[[ -n "$COV_BUILD_ID" ]] || { echo "::error:: no manifest.build_id in ${COV_SRC}" >&2; exit 1; }

if [[ "$COV_BUILD_ID" != "$T" ]]; then
    echo "::error:: release identity mismatch — this deploy tree did not produce ${TAG}." >&2
    echo "::error::   deploy tree      : ${T}" >&2
    echo "::error::   manifest build_id: ${COV_BUILD_ID}" >&2
    echo "::error:: assemble on the host that ran the build, or cut a tag whose manifest names this build." >&2
    if [[ "${ALLOW_BUILD_ID_MISMATCH:-0}" == 1 ]]; then
        echo "::warning:: proceeding (ALLOW_BUILD_ID_MISMATCH=1). THIS OUTPUT IS NOT A VALID RELEASE." >&2
    else
        exit 1
    fi
fi

case "$COV_GENERATED" in
    ""|"<iso8601>")
        echo "::error:: manifest.generated_utc is '${COV_GENERATED}' in ${COV_SRC} — set it before cutting the release." >&2
        exit 1 ;;
esac

if [[ "$COV_BUILD_ID" == "$T" ]]; then
    echo "==> release identity: ${T} matches manifest.build_id  (generated ${COV_GENERATED})"
else
    echo "==> release identity: ${T} does NOT match manifest.build_id ${COV_BUILD_ID}; check overridden (generated ${COV_GENERATED})"
fi

# ---------------------------------------------------------------------------
# Known-issue continuity gate.
#
# Every issue the previous release left open must reappear in this release's
# manifest, still deferred or marked resolved, under the same id. v2.1.0-rc11
# dropped one silently: the lists were carried by copying and nothing
# compared one release with the next (docs/release-notes/v2.1.0-rc11-errata.md).
# ---------------------------------------------------------------------------
echo "==> known-issue continuity"
if ! python3 "${SCRIPT_DIR}/check-known-issues.py" "${SCRIPT_DIR}/.." "$BOARD" "$TAG"; then
    if [[ "${ALLOW_KNOWN_ISSUES_GAP:-0}" == 1 ]]; then
        echo "::warning:: proceeding (ALLOW_KNOWN_ISSUES_GAP=1). THIS OUTPUT IS NOT A VALID RELEASE." >&2
    else
        exit 1
    fi
fi

# ---------------------------------------------------------------------------
# Image identity gate.
#
# The gate above ties the deploy tree to the tag. This one ties the image to
# it. /etc/tactiq-release, read from the release rootfs itself, is what the
# device reports as its identity and the key by which a verifier selects the
# reference for this build. v2.1.0-rc11 shipped reporting v2.1.0-rc9 because
# release-rev.inc was set by hand and nothing read it back
# (docs/release-notes/v2.1.0-rc11-errata.md).
# ---------------------------------------------------------------------------
echo "==> image identity"
command -v debugfs >/dev/null 2>&1 || { echo "::error:: debugfs not on PATH (e2fsprogs), needed to read the release rootfs." >&2; exit 1; }
ROOTFS_EXT4="${DEPLOY}/${PREFIX}.ext4"
IDENTITY="$(debugfs -R "cat /etc/tactiq-release" "$ROOTFS_EXT4" 2>/dev/null || true)"
[[ -n "$IDENTITY" ]] || { echo "::error:: /etc/tactiq-release not found in ${PREFIX}.ext4" >&2; exit 1; }

id_field() {  # echo the value of one KEY=value line of /etc/tactiq-release
    printf '%s\n' "$IDENTITY" | sed -n "s/^$1=//p" | head -n 1
}
ID_VERSION="$(id_field TACTIQ_OS_VERSION)"
ID_MACHINE="$(id_field TACTIQ_BUILD_MACHINE)"
ID_REV="$(id_field TACTIQ_META_TACTIQ_GIT)"
ID_IMAGE="$(id_field TACTIQ_IMAGE_NAME)"
ID_DATE="$(id_field TACTIQ_RELEASE_DATE)"

id_bad=0
id_expect() {  # id_expect <field> <found> <expected>
    if [[ "$2" != "$3" ]]; then
        echo "::error:: /etc/tactiq-release ${1}='${2}', expected '${3}'" >&2
        id_bad=1
    fi
}
id_expect TACTIQ_META_TACTIQ_GIT "$ID_REV"     "$TAG"
id_expect TACTIQ_BUILD_MACHINE   "$ID_MACHINE" "$MACHINE"
id_expect TACTIQ_IMAGE_NAME      "$ID_IMAGE"   "$IMAGE"
if [[ -z "$ID_VERSION" || ( "$TAG" != "v${ID_VERSION}" && "$TAG" != "v${ID_VERSION}-"* ) ]]; then
    echo "::error:: /etc/tactiq-release TACTIQ_OS_VERSION='${ID_VERSION}' does not match tag ${TAG}" >&2
    id_bad=1
fi
if [[ ! "$ID_DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
    echo "::error:: /etc/tactiq-release TACTIQ_RELEASE_DATE='${ID_DATE}' is not a date (YYYY-MM-DD)" >&2
    id_bad=1
fi
if [[ "$id_bad" == 1 ]]; then
    echo "::error:: the image does not identify itself as ${TAG}; set recipes-core/tactiq-release/release-rev.inc in the tagged commit." >&2
    if [[ "${ALLOW_IDENTITY_MISMATCH:-0}" == 1 ]]; then
        echo "::warning:: proceeding (ALLOW_IDENTITY_MISMATCH=1). THIS OUTPUT IS NOT A VALID RELEASE." >&2
    else
        exit 1
    fi
fi
echo "==> image identity: ${ID_REV} ${ID_IMAGE} ${ID_MACHINE} ${ID_DATE}"

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
copy "${PREFIX}.ext4.verity-params"        "verity-${BOARD}.params"
copy "Image-${MACHINE}.bin"                 "kernel-${BOARD}.bin"
copy "rk3588s-rock-5a.dtb"                  "rk3588s-rock-5a.dtb"
copy "${PREFIX}.manifest"                   "manifest-${BOARD}.txt"
copy "${PREFIX}.testdata.json"              "testdata-${BOARD}.json"
copy "${PREFIX}.spdx.json"                  "sbom-${BOARD}.spdx.json"
copy "${PREFIX}.sbom-cve-check.yocto.json"  "cve-${BOARD}.sbom-cve-check.yocto.json"
printf '%s\n' "$IDENTITY" > "tactiq-release-${BOARD}"
echo "    + tactiq-release-${BOARD}  (/etc/tactiq-release from ${PREFIX}.ext4)"

# RAUC OTA bundle. Taken through the per-machine "latest" link and held to the
# same build as the image: a bundle from another build would install bytes the
# rest of this release does not describe. Missing is an error for the release
# image and a warning otherwise.
RAUCB_LINK="${DEPLOY}/tactiq-bundle-${MACHINE}.raucb"
if [[ -e "$RAUCB_LINK" ]]; then
    RAUCB="$(readlink -f "$RAUCB_LINK")"
    if [[ "$(basename "$RAUCB")" != "tactiq-bundle-${MACHINE}-${T}.raucb" ]]; then
        echo "::error:: bundle $(basename "$RAUCB") is not from build ${T}." >&2
        [[ "${ALLOW_MIXED_BUILD:-0}" == 1 ]] || exit 1
        echo "::warning:: proceeding (ALLOW_MIXED_BUILD=1). THIS OUTPUT IS NOT A VALID RELEASE." >&2
    fi
    cp -L "$RAUCB" "bundle-${BOARD}.raucb"
    echo "    + bundle-${BOARD}.raucb  (from $(basename "$RAUCB"))"
elif [[ "$IMAGE" == "tactiq-image" ]]; then
    echo "::error:: no RAUC bundle at ${RAUCB_LINK}; the release ships one." >&2
    exit 1
else
    echo "::warning:: no RAUC bundle at ${RAUCB_LINK} — OTA bundle skipped." >&2
fi

# ---------------------------------------------------------------------------
# Boot PCR reference.
#
# Two producers write the boot partition: the image class (.bootext4, which
# ends up in the .wic a card is first flashed with) and the tactiq-boot-image
# recipe (which the RAUC bundle installs into a slot). A reference derived from
# one is only valid for a board prepared with the other if both carry the same
# bytes, so both are opened and compared before anything is derived. The FIT
# and extlinux.conf are published as found on the boot partition, next to the
# bootloader and its default environment, so a reader can rerun the
# computation from release assets alone.
# ---------------------------------------------------------------------------
echo "==> boot PCR reference"
command -v debugfs >/dev/null 2>&1 || { echo "::error:: debugfs not on PATH (e2fsprogs) — needed to read the boot partition." >&2; exit 1; }
BOOT_CLASS="${DEPLOY}/${PREFIX}.bootext4"
BOOT_RECIPE="${DEPLOY}/tactiq-boot-image.ext4"
[[ -e "$BOOT_CLASS" ]]  || { echo "::error:: missing artifact: $BOOT_CLASS" >&2; exit 1; }
[[ -e "$BOOT_RECIPE" ]] || { echo "::error:: missing artifact: $BOOT_RECIPE" >&2; exit 1; }
[[ -e "$BOOT_ENV" ]]    || { echo "::error:: boot environment not found: $BOOT_ENV" >&2; exit 1; }

BOOTX="$(mktemp -d)"
trap 'rm -rf "$BOOTX"' EXIT
extract() {  # extract <ext4-image> <path-in-image> <dest>
    debugfs -R "dump $2 $3" "$1" >/dev/null 2>&1 || true
    [[ -s "$3" ]] || { echo "::error:: $2 not found in $(basename "$1")" >&2; exit 1; }
}
for f in fitImage boot/extlinux/extlinux.conf; do
    n="$(basename "$f")"
    extract "$BOOT_CLASS"  "/$f" "${BOOTX}/class-${n}"
    extract "$BOOT_RECIPE" "/$f" "${BOOTX}/recipe-${n}"
    if ! cmp -s "${BOOTX}/class-${n}" "${BOOTX}/recipe-${n}"; then
        echo "::error:: /$f differs between $(basename "$BOOT_CLASS") and $(basename "$BOOT_RECIPE")." >&2
        echo "::error:: a card flashed from the .wic and a slot installed from the bundle would boot different bytes." >&2
        exit 1
    fi
done
cp "${BOOTX}/recipe-fitImage"      "fitImage-${BOARD}";      echo "    + fitImage-${BOARD}"
cp "${BOOTX}/recipe-extlinux.conf" "extlinux-${BOARD}.conf"; echo "    + extlinux-${BOARD}.conf"
copy "idbloader.img"                "idbloader-${BOARD}.img"
copy "u-boot.itb"                   "u-boot-${BOARD}.itb"
cp -L "$BOOT_ENV" "tactiq-boot-${BOARD}.env";               echo "    + tactiq-boot-${BOARD}.env"
cp -L "${SCRIPT_DIR}/mk-pcr-reference.py" "mk-pcr-reference.py"; echo "    + mk-pcr-reference.py"

python3 mk-pcr-reference.py \
    --fit "fitImage-${BOARD}" --extlinux "extlinux-${BOARD}.conf" \
    --uboot "u-boot-${BOARD}.itb" --idbloader "idbloader-${BOARD}.img" \
    --boot-env "tactiq-boot-${BOARD}.env" \
    --image "kernel-${BOARD}.bin" --dtb "rk3588s-rock-5a.dtb" \
    --out "pcr-reference-${BOARD}.json"
echo "    + pcr-reference-${BOARD}.json"

FIT_KEY="$(python3 -c 'import json,sys; print(",".join(json.load(open(sys.argv[1]))["components"]["fit_key_name_hint"]))' "pcr-reference-${BOARD}.json")"
echo "    FIT signed with: ${FIT_KEY}"
if [[ "$IMAGE" == "tactiq-image" && "$FIT_KEY" == "dev-fit" ]]; then
    if [[ "${ALLOW_DEV_FIT_KEY:-0}" == 1 ]]; then
        echo "::warning:: release FIT is signed with the development key (ALLOW_DEV_FIT_KEY=1). THIS OUTPUT IS NOT A VALID RELEASE." >&2
    else
        echo "::error:: release FIT is signed with the development key dev-fit, whose private half is public." >&2
        echo "::error:: point TACTIQ_FIT_KEY_DIR at the release key, or set ALLOW_DEV_FIT_KEY=1 to test mechanics." >&2
        exit 1
    fi
fi

# buildinfo — full bitbake datastore snapshot (distro / layers / versions /
# SRCREVs). Provenance and reproducibility input; needs the build env sourced.
if [[ "${SKIP_BUILDINFO:-0}" != 1 && "$FIT_KEY" != "dev-fit" && -z "${BUILDINFO_CONF:-}" ]]; then
    echo "::error:: FIT signed with ${FIT_KEY}, but BUILDINFO_CONF is not set." >&2
    echo "::error:: bitbake -e without the -R file the image was built with would record the development configuration." >&2
    exit 1
fi
if [[ "${SKIP_BUILDINFO:-0}" == 1 ]]; then
    echo "::warning:: SKIP_BUILDINFO=1 — buildinfo-${BOARD}.json omitted." >&2
elif command -v bitbake >/dev/null 2>&1; then
    echo "==> buildinfo (bitbake -e ${IMAGE})"
    TMPENV="$(mktemp)"; bitbake ${BUILDINFO_CONF:+-R "$BUILDINFO_CONF"} -e "$IMAGE" > "$TMPENV"
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
# ---------------------------------------------------------------------------
# Threat-coverage manifest — hand-authored map, version-pinned to this tag.
# Copied from the repo tree (NOT the Yocto deploy) so its hash lands in the
# globbed SHA256SUMS below and rides the keyless release signature. Hard-fail
# if absent: a transparency release without its coverage map is a defect.
# ---------------------------------------------------------------------------
echo "==> coverage manifest"
# COV_SRC resolved and validated by the release-identity gate above.
cp -L "$COV_SRC" "coverage-${BOARD}.${TAG}.yaml"
echo "    + coverage-${BOARD}.${TAG}.yaml"
# ---------------------------------------------------------------------------
# Reference Integrity Manifest (RELEASE_INTEGRITY.md 5). mk-rim.py builds
# rim-<board>.json from files already in the set (identity, PCR reference,
# FIT, u-boot.itb, idbloader), the RAUC keyring and, where installed, the IMA
# certificate read from the release rootfs, the release root certificate, and
# the platform disclosures of security/rim-disclosures-<board>.txt, and the
# attestation agent's unit from the release rootfs, whose PCR set must equal the
# RIM selection. It is signed with the RIM leaf
# of the release Signing CA (gen-pki.sh rim / rim-prod): CMS, detached, DER,
# no signed attributes, sha256; the container carries the leaf and the Signing
# CA. Both files land in SHA256SUMS below and ride the keyless release
# signature on top.
#   RIM_SIGNER_CERT, RIM_SIGNER_KEY  the RIM leaf and its key (the key may be
#                                    encrypted: openssl asks for the password)
#   RIM_SIGNING_CA                   the Signing CA certificate
#   RIM_ROOT_CA                      the release root certificate; required
#                                    with RIM_SIGNER_CERT, fingerprinted into
#                                    the RIM and used to verify the signature
#   ALLOW_NO_RIM=1                   let IMAGE=tactiq-image go without a signed
#                                    RIM or its disclosures file (mechanics only)
# Witness fields (no part in RIM selection): build_label is the pinned build
# timestamp ${T}; tag_commit is the full SHA of refs/tags/${TAG} in this tree.
# ---------------------------------------------------------------------------
echo "==> RIM"
RIM_EKU="2.25.209288284150790823604684143005475146259"
RIM_KEYRING_PATH="/etc/rauc/root-ca.pem"   # recipes-core/rauc/files/system.conf [keyring] path
RIM_IMA_PATH="/etc/keys/x509_ima.der"      # kernel default CONFIG_IMA_X509_PATH
RIM_AGENT_PATH="/usr/lib/systemd/system/tactiq-agent.service"  # usrmerge: systemd_system_unitdir
RIM_DISCLOSURES="$(cd "${SCRIPT_DIR}/.." && pwd)/security/rim-disclosures-${BOARD}.txt"
rootfs_dump() {  # rootfs_dump <path-in-rootfs> <dest>: 0 dumped, 2 absent, 1 present but unreadable; follows symlinks
    local p="$1" dst="$2" st dest n
    for n in 1 2 3 4 5 6 7 8; do
        st="$(DEBUGFS_PAGER=__none__ debugfs -R "stat ${p}" "$ROOTFS_EXT4" 2>/dev/null || true)"
        if [[ -z "$st" ]]; then
            [[ "$p" == "$1" ]] && return 2 || return 1   # a dangling link is unreadable, not absent
        fi
        if [[ "$st" =~ Type:\ regular ]]; then
            : > "$dst"
            DEBUGFS_PAGER=__none__ debugfs -R "dump ${p} ${dst}" "$ROOTFS_EXT4" >/dev/null 2>&1 || true
            [[ -s "$dst" ]] && return 0 || return 1
        elif [[ "$st" =~ Type:\ symlink ]]; then
            if [[ "$st" =~ Fast\ link\ dest:\ \"([^\"]*)\" ]]; then
                dest="${BASH_REMATCH[1]}"
            else
                dest="$(DEBUGFS_PAGER=__none__ debugfs -R "cat ${p}" "$ROOTFS_EXT4" 2>/dev/null || true)"
            fi
            [[ -n "$dest" ]] || return 1
            if [[ "$dest" == /* ]]; then p="$dest"; else p="$(dirname "$p")/${dest}"; fi
        else
            return 1
        fi
    done
    return 1
}
rim_no_rim() {  # a RIM requirement is missing: fatal for a release image unless ALLOW_NO_RIM=1
    if [[ "$IMAGE" == tactiq-image && "${ALLOW_NO_RIM:-0}" != 1 ]]; then
        echo "::error:: $1 (ALLOW_NO_RIM=1 for mechanics only)" >&2
        exit 1
    fi
    echo "::warning:: $1" >&2
}
rim_witness=( --witness "build_label=${T}" )
RIM_TAG_COMMIT="$(git -C "${SCRIPT_DIR}/.." rev-parse --verify -q "refs/tags/${TAG}^{commit}" 2>/dev/null || true)"
if [[ -n "$RIM_TAG_COMMIT" ]]; then
    rim_witness+=( --witness "tag_commit=${RIM_TAG_COMMIT}" )
elif [[ "$IMAGE" == tactiq-image ]]; then
    echo "::error:: tag ${TAG} is not in $(cd "${SCRIPT_DIR}/.." && pwd); a release RIM must name the tagged commit." >&2
    exit 1
else
    echo "::warning:: tag ${TAG} not in this tree; RIM witness carries no tag_commit." >&2
fi
rim_args=()
if [[ -f "$RIM_DISCLOSURES" ]]; then
    rim_args+=( --disclosures "$RIM_DISCLOSURES" )
else
    rim_no_rim "no platform disclosures: ${RIM_DISCLOSURES} is absent"
fi
if [[ -n "${RIM_SIGNER_CERT:-}" ]]; then
    [[ -n "${RIM_ROOT_CA:-}" && -r "${RIM_ROOT_CA}" ]] \
        || { echo "::error:: RIM_SIGNER_CERT is set but RIM_ROOT_CA is not, or is unreadable." >&2; exit 1; }
fi
[[ -n "${RIM_ROOT_CA:-}" ]] && rim_args+=( --release-root "$RIM_ROOT_CA" )
RIM_KEYRING="$(mktemp)"; RIM_IMA="$(mktemp)"; RIM_AGENT="$(mktemp)"
rim_rc=0; rootfs_dump "$RIM_KEYRING_PATH" "$RIM_KEYRING" || rim_rc=$?
if [[ "$rim_rc" != 0 ]]; then
    rm -f -- "$RIM_KEYRING" "$RIM_IMA" "$RIM_AGENT"
    echo "::error:: ${RIM_KEYRING_PATH} is $([[ $rim_rc == 2 ]] && echo absent || echo unreadable) in ${PREFIX}.ext4" >&2
    exit 1
fi
rim_rc=0; rootfs_dump "$RIM_IMA_PATH" "$RIM_IMA" || rim_rc=$?
case "$rim_rc" in
    0)  rim_args+=( --ima-cert "$RIM_IMA" --ima-cert-path "$RIM_IMA_PATH" )
        echo "    IMA certificate: ${RIM_IMA_PATH}  (sha256 $(sha256sum "$RIM_IMA" | cut -c1-16)...)" ;;
    2)  echo "    IMA certificate: none installed at ${RIM_IMA_PATH}" ;;
    *)  rm -f -- "$RIM_KEYRING" "$RIM_IMA" "$RIM_AGENT"
        echo "::error:: ${RIM_IMA_PATH} exists in ${PREFIX}.ext4 but does not resolve to a readable file" >&2
        exit 1 ;;
esac
rim_rc=0; rootfs_dump "$RIM_AGENT_PATH" "$RIM_AGENT" || rim_rc=$?
case "$rim_rc" in
    0)  rim_args+=( --agent-unit "$RIM_AGENT" ) ;;
    2)  rim_no_rim "no attestation agent unit at ${RIM_AGENT_PATH}: the PCR set a device quotes is unchecked" ;;
    *)  rm -f -- "$RIM_KEYRING" "$RIM_IMA" "$RIM_AGENT"
        echo "::error:: ${RIM_AGENT_PATH} exists in ${PREFIX}.ext4 but does not resolve to a readable file" >&2
        exit 1 ;;
esac
python3 "${SCRIPT_DIR}/mk-rim.py" \
    --identity "tactiq-release-${BOARD}" \
    --pcr-reference "pcr-reference-${BOARD}.json" \
    --fit "fitImage-${BOARD}" --uboot "u-boot-${BOARD}.itb" \
    --idbloader "idbloader-${BOARD}.img" \
    --rauc-keyring "$RIM_KEYRING" --rauc-keyring-path "$RIM_KEYRING_PATH" \
    "${rim_witness[@]}" "${rim_args[@]}" \
    -o "rim-${BOARD}.json" || { rm -f -- "$RIM_KEYRING" "$RIM_IMA" "$RIM_AGENT"; exit 1; }
rm -f -- "$RIM_KEYRING" "$RIM_IMA" "$RIM_AGENT"
echo "    + rim-${BOARD}.json"
if [[ -n "${RIM_SIGNER_CERT:-}" ]]; then
    for v in RIM_SIGNER_KEY RIM_SIGNING_CA; do
        [[ -n "${!v:-}" && -r "${!v}" ]] || { echo "::error:: RIM_SIGNER_CERT is set but ${v} is not, or is unreadable." >&2; exit 1; }
    done
    if ! openssl x509 -in "$RIM_SIGNER_CERT" -noout -ext extendedKeyUsage 2>/dev/null | grep -qx "[[:space:]]*${RIM_EKU}"; then
        echo "::error:: ${RIM_SIGNER_CERT} is not a RIM leaf: its only EKU must be ${RIM_EKU}." >&2
        exit 1
    fi
    openssl verify -CAfile "$RIM_ROOT_CA" -untrusted "$RIM_SIGNING_CA" "$RIM_SIGNER_CERT" >/dev/null \
        || { echo "::error:: ${RIM_SIGNER_CERT} does not chain to RIM_ROOT_CA through RIM_SIGNING_CA." >&2; exit 1; }
    openssl cms -sign -binary -noattr -md sha256 \
        -in "rim-${BOARD}.json" -signer "$RIM_SIGNER_CERT" -inkey "$RIM_SIGNER_KEY" \
        -certfile "$RIM_SIGNING_CA" -outform DER -out "rim-${BOARD}.json.p7s"
    openssl cms -verify -binary -inform DER -in "rim-${BOARD}.json.p7s" \
        -content "rim-${BOARD}.json" -CAfile "$RIM_ROOT_CA" \
        -purpose any -out /dev/null 2>/dev/null \
        || { echo "::error:: rim-${BOARD}.json.p7s does not verify to RIM_ROOT_CA." >&2; exit 1; }
    echo "    + rim-${BOARD}.json.p7s  ($(openssl x509 -in "$RIM_SIGNER_CERT" -noout -subject -nameopt RFC2253 | sed 's/^subject=//'))"
else
    rim_no_rim "RIM left unsigned: set RIM_SIGNER_CERT, RIM_SIGNER_KEY, RIM_SIGNING_CA, RIM_ROOT_CA"
fi
echo "==> SHA256SUMS"
# SHA256SUMS does not exist yet, so the glob below cannot include it.
shopt -s nullglob; files=( * ); shopt -u nullglob
# Copies inherit the mode of their source, which on some hosts is 0777.
# Normalise: data 0644, the one script 0755.
[[ ${#files[@]} -gt 0 ]] || { echo "::error:: no artifacts to hash" >&2; exit 1; }
chmod 0644 -- "${files[@]}"
chmod 0755 -- mk-pcr-reference.py
sha256sum -- "${files[@]}" | LC_ALL=C sort -k2 > SHA256SUMS

echo "==> done: ${OUT}  (tag ${TAG})"
ls -la "$OUT"
