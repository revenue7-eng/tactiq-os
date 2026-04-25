SUMMARY = "TactiQ OS Configuration Files"
LICENSE = "GPL-3.0-or-later"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/GPL-3.0-or-later;md5=1ebbd3e34237af26da5dc08a4e440464"

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
