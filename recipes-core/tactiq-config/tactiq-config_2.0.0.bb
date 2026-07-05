SUMMARY = "TactiQ OS Configuration Files"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "file://agent.yaml \
           file://data-tactiq-dirs.service \
           file://data.mount \
          "

UNPACKDIR = "${WORKDIR}/sources"

inherit systemd

SYSTEMD_SERVICE:${PN} = "data.mount data-tactiq-dirs.service"
SYSTEMD_AUTO_ENABLE:${PN} = "enable"

do_install() {
    # Agent config
    install -d ${D}/etc/tactiq
    install -m 0644 ${UNPACKDIR}/agent.yaml ${D}/etc/tactiq/agent.yaml

    # Systemd units
    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${UNPACKDIR}/data-tactiq-dirs.service ${D}${systemd_system_unitdir}/data-tactiq-dirs.service
    install -m 0644 ${UNPACKDIR}/data.mount ${D}${systemd_system_unitdir}/data.mount

    # Mount point (empty)
    install -d ${D}/data
}

FILES:${PN} = " \
    /etc/tactiq \
    ${systemd_system_unitdir}/data-tactiq-dirs.service \
    ${systemd_system_unitdir}/data.mount \
    /data \
"
CONFFILES:${PN} = "/etc/tactiq/agent.yaml"
