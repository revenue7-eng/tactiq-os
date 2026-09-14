SUMMARY = "TactiQ OS Configuration Files"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "file://agent.yaml \
           file://data-tactiq-dirs.service \
           file://data.mount \
           file://10-tactiq-watchdog.conf \
           file://10-tactiq-printk.conf \
           file://10-tactiq-hardening.conf \
           file://20-tactiq-journal.conf \
           file://tactiq-log-setup.service \
           file://tactiq-log-setup.sh \
           file://var-volatile-log-journal.mount \
          "

UNPACKDIR = "${WORKDIR}/sources"
S = "${UNPACKDIR}"

inherit systemd

SYSTEMD_SERVICE:${PN} = "data.mount data-tactiq-dirs.service tactiq-log-setup.service var-volatile-log-journal.mount"
SYSTEMD_AUTO_ENABLE:${PN} = "enable"

do_install() {
    # Agent config
    install -d ${D}/etc/tactiq
    install -m 0644 ${UNPACKDIR}/agent.yaml ${D}/etc/tactiq/agent.yaml

    # Systemd units
    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${UNPACKDIR}/data-tactiq-dirs.service ${D}${systemd_system_unitdir}/data-tactiq-dirs.service
    install -m 0644 ${UNPACKDIR}/data.mount ${D}${systemd_system_unitdir}/data.mount
    install -m 0644 ${UNPACKDIR}/tactiq-log-setup.service ${D}${systemd_system_unitdir}/tactiq-log-setup.service
    install -m 0644 ${UNPACKDIR}/var-volatile-log-journal.mount ${D}${systemd_system_unitdir}/var-volatile-log-journal.mount
    install -d ${D}${systemd_unitdir}/system.conf.d
    install -m 0644 ${UNPACKDIR}/10-tactiq-watchdog.conf ${D}${systemd_unitdir}/system.conf.d/10-tactiq-watchdog.conf

    # Level 0 logging: journald drop-in + the setup the drop-in depends on
    install -d ${D}${systemd_unitdir}/journald.conf.d
    install -m 0644 ${UNPACKDIR}/20-tactiq-journal.conf ${D}${systemd_unitdir}/journald.conf.d/20-tactiq-journal.conf
    install -d ${D}${sbindir}
    install -m 0755 ${UNPACKDIR}/tactiq-log-setup.sh ${D}${sbindir}/tactiq-log-setup

    # Console log level (see the file for why)
    install -d ${D}${sysconfdir}/sysctl.d
    install -m 0644 ${UNPACKDIR}/10-tactiq-printk.conf ${D}${sysconfdir}/sysctl.d/10-tactiq-printk.conf

    # Runtime hardening sysctls (see the file for why)
    install -m 0644 ${UNPACKDIR}/10-tactiq-hardening.conf ${D}${sysconfdir}/sysctl.d/10-tactiq-hardening.conf

    # Mount point (empty)
    install -d ${D}/data
}

FILES:${PN} = " \
    /etc/tactiq \
    ${systemd_system_unitdir}/data-tactiq-dirs.service \
    ${systemd_system_unitdir}/data.mount \
    ${systemd_system_unitdir}/tactiq-log-setup.service \
    ${systemd_system_unitdir}/var-volatile-log-journal.mount \
    ${systemd_unitdir}/journald.conf.d/20-tactiq-journal.conf \
    ${sbindir}/tactiq-log-setup \
    ${systemd_unitdir}/system.conf.d/10-tactiq-watchdog.conf \
    ${sysconfdir}/sysctl.d/10-tactiq-printk.conf \
    ${sysconfdir}/sysctl.d/10-tactiq-hardening.conf \
    /data \
"
CONFFILES:${PN} = "/etc/tactiq/agent.yaml ${sysconfdir}/sysctl.d/10-tactiq-printk.conf ${sysconfdir}/sysctl.d/10-tactiq-hardening.conf"
