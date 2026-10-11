SUMMARY = "Trust anchor for Edge cartridge signatures"
DESCRIPTION = "Installs the certificate the Edge daemon checks cartridge \
signatures against. The development default is the in-tree root; a \
production build must point TACTIQ_CARTRIDGE_ANCHOR at the release root \
outside the tree, and tactiq-keygate halts parsing if it does not. The \
daemon does not check certificate validity dates: the board clock is not \
trusted, and revocation is an OS release that changes this anchor."
HOMEPAGE = "https://github.com/revenue7-eng/tactiq-os"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

INHIBIT_DEFAULT_DEPS = "1"
ALLOW_EMPTY:${PN} = "0"

do_configure[noexec] = "1"
do_compile[noexec] = "1"

do_install() {
    install -d ${D}${sysconfdir}/tactiq/cartridge-anchor
    install -m 0644 ${TACTIQ_CARTRIDGE_ANCHOR} ${D}${sysconfdir}/tactiq/cartridge-anchor/root-ca.pem
}
do_install[file-checksums] += "${TACTIQ_CARTRIDGE_ANCHOR}:True"

FILES:${PN} = "${sysconfdir}/tactiq/cartridge-anchor/root-ca.pem"
