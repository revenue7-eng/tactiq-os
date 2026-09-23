# tactiq-release-identity.bbclass: write /etc/tactiq-release into the rootfs.
#
# Build identity is a property of the image, not of a package. Until
# v2.1.0-rc11 the file came from the tactiq-release package, which cannot
# know which image it lands in: TACTIQ_IMAGE_NAME expanded to nothing, and
# the same package went into the development and the production profile. An
# image writing the file after package installation would instead leave the
# package's SPDX record describing a file the rootfs no longer holds. So the
# image writes it, whole, and no package claims it.
#
# The file is what a device reports as its identity and the key by which a
# verifier selects the reference integrity manifest of its build
# (RELEASE_INTEGRITY.md section 5.4). Two rules follow:
#   1. Every value is static, so two builds at the same source state write
#      byte-identical files.
#   2. Nothing shells out to git on the build host: the release tag and date
#      are declared in release-rev.inc and travel with the tag.
#
# scripts/mk-release.sh reads the file back from the release rootfs and
# refuses a release whose image does not name the tag being released.
#
# The function runs in ROOTFS_POSTPROCESS_COMMAND, before SELinux labelling
# and before IMA signing in the development profile, both of which run in
# IMAGE_PREPROCESS_COMMAND, so the file is labelled and signed like any other.

require recipes-core/tactiq-release/release-rev.inc

# TACTIQ_META_GIT_REV in the environment still takes precedence, for
# development builds from a working tree that is not at a release.
TACTIQ_META_GIT_REV ??= "${@os.environ.get('TACTIQ_META_GIT_REV') or d.getVar('TACTIQ_OS_RELEASE_REV') or 'unknown'}"
TACTIQ_RELEASE_DATE ??= "${@d.getVar('TACTIQ_OS_RELEASE_DATE') or 'unknown'}"

# Hash the expanded values, so a changed tag or date reruns do_rootfs instead
# of reusing a rootfs that names the previous one.
TACTIQ_META_GIT_REV[vardepvalue] = "${TACTIQ_META_GIT_REV}"
TACTIQ_RELEASE_DATE[vardepvalue] = "${TACTIQ_RELEASE_DATE}"
do_rootfs[vardeps] += "TACTIQ_META_GIT_REV TACTIQ_RELEASE_DATE"

python __anonymous() {
    for v in ('TACTIQ_META_GIT_REV', 'TACTIQ_RELEASE_DATE'):
        if d.getVar(v) == 'unknown':
            bb.note('%s is unknown: release-rev.inc carries no value; '
                    '/etc/tactiq-release will record "unknown"' % v)
}

tactiq_write_release() {
    install -d ${IMAGE_ROOTFS}${sysconfdir}
    cat > ${IMAGE_ROOTFS}${sysconfdir}/tactiq-release << RELEASE
TACTIQ_OS_VERSION=${DISTRO_VERSION}
TACTIQ_OS_CODENAME=${DISTRO_CODENAME}
TACTIQ_BUILD_MACHINE=${MACHINE}
TACTIQ_META_TACTIQ_GIT=${TACTIQ_META_GIT_REV}
TACTIQ_IMAGE_NAME=${IMAGE_BASENAME}
TACTIQ_RELEASE_DATE=${TACTIQ_RELEASE_DATE}
RELEASE
    chmod 0644 ${IMAGE_ROOTFS}${sysconfdir}/tactiq-release
}

ROOTFS_POSTPROCESS_COMMAND += "tactiq_write_release"
