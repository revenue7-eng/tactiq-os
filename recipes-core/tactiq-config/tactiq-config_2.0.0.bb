SUMMARY = "TactiQ OS Configuration Files"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "file://agent.yaml \
           file://data-tactiq-dirs.service \
          "

S = "${WORKDIR}"

inherit systemd

SYSTEMD_SERVICE:${PN} = "data-tactiq-dirs.service"
SYSTEMD_AUTO_ENABLE:${PN} = "enable"

do_install() {
    # Agent config
    install -d ${D}/etc/tactiq
    install -m 0644 ${WORKDIR}/agent.yaml ${D}/etc/tactiq/agent.yaml

    # Systemd units
    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${WORKDIR}/data-tactiq-dirs.service ${D}${systemd_system_unitdir}/data-tactiq-dirs.service

    # Mount point (empty)
    install -d ${D}/data
}

FILES:${PN} = " \
    /etc/tactiq \
    ${systemd_system_unitdir}/data-tactiq-dirs.service \
    /data \
"
CONFFILES:${PN} = "/etc/tactiq/agent.yaml"
