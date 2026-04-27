SUMMARY = "TactiQ OS Release Information"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

S = "${WORKDIR}"

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
# The commit revision is read from TACTIQ_META_GIT_REV, which the CI
# release pipeline sets explicitly at build time (e.g. from the tag
# ref). For local development builds without the variable set, the
# recipe records 'unknown' and emits a build-time NOTE so that an
# operator does not silently ship an attestation that mis-identifies
# the build.
#
# The build date is derived from SOURCE_DATE_EPOCH so it tracks the
# Yocto reproducibility plumbing rather than the wall-clock at build.

TACTIQ_META_GIT_REV ??= "${@os.environ.get('TACTIQ_META_GIT_REV', 'unknown')}"

python __anonymous() {
    if d.getVar('TACTIQ_META_GIT_REV') == 'unknown':
        bb.note('TACTIQ_META_GIT_REV is unset; /etc/tactiq-release will record "unknown"')
}

do_compile() {
    # SOURCE_DATE_EPOCH is set by Yocto reproducibility machinery;
    # fall back to 0 (1970-01-01) only if entirely absent — this is
    # the same convention image-buildinfo uses.
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
