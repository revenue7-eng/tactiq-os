SUMMARY = "TactiQ OS Release Information"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

S = "${WORKDIR}"

inherit image-buildinfo

do_compile() {
    cat > ${S}/tactiq-release << RELEASE
TACTIQ_OS_VERSION=${DISTRO_VERSION}
TACTIQ_OS_CODENAME=${DISTRO_CODENAME}
TACTIQ_BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ)
TACTIQ_BUILD_MACHINE=${MACHINE}
TACTIQ_META_TACTIQ_GIT=$(cd ${THISDIR}/../../.. && git rev-parse --short HEAD 2>/dev/null || echo "unknown")
TACTIQ_IMAGE_NAME=${IMAGE_BASENAME}
RELEASE
}

do_install() {
    install -d ${D}/etc
    install -m 0644 ${S}/tactiq-release ${D}/etc/tactiq-release
}

FILES:${PN} = "/etc/tactiq-release"
