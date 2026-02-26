SUMMARY = "TactiQ OS Configuration Files"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "file://agent.yaml \
           file://data-tactiq-counter.conf \
          "

S = "${WORKDIR}"

do_install() {
    # Agent config
    install -d ${D}/etc/tactiq
    install -m 0644 ${WORKDIR}/agent.yaml ${D}/etc/tactiq/agent.yaml

    # Static data dirs (keys/certs on read-only rootfs)
    install -d ${D}/data/tactiq/keys
    install -d ${D}/data/tactiq/certs

    # tmpfiles.d for writable dirs (counter/audit on tmpfs)
    install -d ${D}${sysconfdir}/tmpfiles.d
    install -m 0644 ${WORKDIR}/data-tactiq-counter.conf ${D}${sysconfdir}/tmpfiles.d/
}

FILES:${PN} = "/etc/tactiq /data/tactiq /etc/tmpfiles.d"
CONFFILES:${PN} = "/etc/tactiq/agent.yaml"
