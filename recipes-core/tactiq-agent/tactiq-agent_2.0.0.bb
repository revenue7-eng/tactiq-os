SUMMARY = "TactiQ Attestation Agent"
DESCRIPTION = "Secure attestation agent with Ed25519 signing"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

inherit systemd

SRC_URI = "file://tactiq-agent.service \
           file://tactiq-agent-stub.sh \
          "

do_install() {
    install -d ${D}/opt/tactiq/bin
    install -m 0755 ${WORKDIR}/tactiq-agent-stub.sh ${D}/opt/tactiq/bin/tactiq-agent

    install -d ${D}${systemd_unitdir}/system
    install -m 0644 ${WORKDIR}/tactiq-agent.service ${D}${systemd_unitdir}/system/

    install -d -m 0700 ${D}/data/tactiq/keys
    install -d ${D}/data/tactiq/audit
    install -d ${D}/data/tactiq/certs
    install -d ${D}/data/tactiq/counter
}

SYSTEMD_SERVICE:${PN} = "tactiq-agent.service"
SYSTEMD_AUTO_ENABLE = "enable"

RDEPENDS:${PN} = "ca-certificates"

FILES:${PN} = " \
    /opt/tactiq/bin/tactiq-agent \
    ${systemd_unitdir}/system/tactiq-agent.service \
    /data/tactiq \
"
