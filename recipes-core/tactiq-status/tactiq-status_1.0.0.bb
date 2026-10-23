SUMMARY = "Device status screen for TactiQ OS"
DESCRIPTION = "tactiq-status prints what the device reports about its own \
boot and integrity state (release, slot, root device, SELinux mode, IMA \
policy, TPM, PCR 0-9 composite, agent and envelope count), read from the \
running system each time. It is a self-report and says so on screen: the \
claim is checked outside the device with VERIFY-L3 against the signed \
release set. A profile.d hook shows it at interactive login."
HOMEPAGE = "https://github.com/revenue7-eng/tactiq-os"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"
SPDX_PACKAGE_SUPPLIER_ref = "SPDX_SUPPLIER_tactiq"

SRC_URI = "file://tactiq-status \
           file://tactiq-status.sh \
          "

UNPACKDIR = "${WORKDIR}/sources"
S = "${UNPACKDIR}"

do_install() {
    install -d ${D}${bindir}
    install -m 0755 ${UNPACKDIR}/tactiq-status ${D}${bindir}/tactiq-status
    install -d ${D}${sysconfdir}/profile.d
    install -m 0644 ${UNPACKDIR}/tactiq-status.sh ${D}${sysconfdir}/profile.d/tactiq-status.sh
}

# Plain shell over files in /proc and /sys. tpm2-tools and systemctl are used
# when present and reported as missing when not, so neither is a dependency:
# the screen must not pull a package into an image.
RDEPENDS:${PN} = ""
