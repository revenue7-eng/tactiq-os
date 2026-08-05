SUMMARY = "TactiQ OS Release Information"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

S = "${UNPACKDIR}"

inherit image-buildinfo

# Build identity is part of the attestation payload. Two principles
# apply:
#   1. The values must be reproducible — two builds at the same source
#      state must produce byte-identical /etc/tactiq-release.
#   2. The values must not be sourced by shelling out to git on the
#      build host inside do_compile, because (a) that is non-
#      deterministic in shallow clones / tar-archived sources and
#      (b) it lets a compromised build host inject a forged commit
#      hash into the attestation chain.
#
# The revision is carried by release-rev.inc, a file in this repository,
# so that it arrives with the tag rather than depending on the person
# running the build remembering to set something. Anyone who clones a
# release tag and builds it gets the same /etc/tactiq-release as we do,
# with no extra step. Principle 2 is unaffected: nothing shells out to
# git, the value is declared in the source tree and travels under the
# same signature as the rest of it.
#
# TACTIQ_META_GIT_REV still takes precedence when set in the environment,
# for development builds from a working tree that is not at a release.
# Where neither is available the recipe records 'unknown' and emits a
# build-time NOTE, so that an operator does not silently ship an
# attestation that mis-identifies the build.
#
# The build date is derived from SOURCE_DATE_EPOCH so it tracks the
# Yocto reproducibility plumbing rather than the wall-clock at build.

require ${THISDIR}/release-rev.inc

TACTIQ_META_GIT_REV ??= "${@os.environ.get('TACTIQ_META_GIT_REV') or d.getVar('TACTIQ_OS_RELEASE_REV') or 'unknown'}"

python __anonymous() {
    if d.getVar('TACTIQ_META_GIT_REV') == 'unknown':
        bb.note('No release revision: release-rev.inc carries none and '
                'TACTIQ_META_GIT_REV is unset; /etc/tactiq-release will '
                'record "unknown"')
}

do_compile() {
    # SOURCE_DATE_EPOCH is set by Yocto reproducibility machinery;
    # fall back to 0 (1970-01-01) only if entirely absent — this is
    # the same convention image-buildinfo uses.
    mkdir -p ${S}
    sde="${SOURCE_DATE_EPOCH}"
    if [ -z "$sde" ]; then sde=0; fi
    build_date=$(date -u -d "@$sde" +%Y-%m-%dT%H:%M:%SZ)

    cat > ${S}/tactiq-release << RELEASE
TACTIQ_OS_VERSION=${DISTRO_VERSION}
TACTIQ_OS_CODENAME=${DISTRO_CODENAME}
TACTIQ_BUILD_DATE=${build_date}
TACTIQ_BUILD_MACHINE=${MACHINE}
TACTIQ_META_TACTIQ_GIT=${TACTIQ_META_GIT_REV}
TACTIQ_IMAGE_NAME=${IMAGE_BASENAME}
RELEASE
}

do_install() {
    install -d ${D}/etc
    install -m 0644 ${S}/tactiq-release ${D}/etc/tactiq-release
}

FILES:${PN} = "/etc/tactiq-release"
