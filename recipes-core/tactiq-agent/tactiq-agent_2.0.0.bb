SUMMARY = "TactiQ Attestation Agent"
DESCRIPTION = "Secure attestation agent with Ed25519 signing"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

inherit systemd useradd

# Create an unprivileged tactiq-agent user/group. The systemd unit runs
# under this user; the agent's TPM device access is granted explicitly
# in the unit (DeviceAllow=/dev/tpmrm0) and through the SELinux policy
# tactiq_agent_t domain.
USERADD_PACKAGES = "${PN}"
USERADD_PARAM:${PN} = "--system --no-create-home --shell /sbin/nologin \
                       --home-dir /var/lib/tactiq-agent -g tactiq-agent \
                       tactiq-agent"
GROUPADD_PARAM:${PN} = "--system tactiq-agent"

SRC_URI = "file://tactiq-agent.service \
           file://tactiq-agent-stub.sh \
          "

do_install() {
    install -d ${D}/opt/tactiq/bin
    install -m 0755 ${UNPACKDIR}/tactiq-agent-stub.sh ${D}/opt/tactiq/bin/tactiq-agent

    install -d ${D}${systemd_unitdir}/system
    install -m 0644 ${UNPACKDIR}/tactiq-agent.service ${D}${systemd_unitdir}/system/

    # /data/tactiq directories are owned by tactiq-agent. The data-
    # tactiq-dirs.service unit ensures the runtime mount is in place
    # before the agent starts (declared via After= and RequiresMountsFor=
    # in the .service file).
    install -d -m 0700 -o tactiq-agent -g tactiq-agent ${D}/data/tactiq/keys
    install -d -m 0750 -o tactiq-agent -g tactiq-agent ${D}/data/tactiq/audit
    install -d -m 0755 -o tactiq-agent -g tactiq-agent ${D}/data/tactiq/certs
    install -d -m 0700 -o tactiq-agent -g tactiq-agent ${D}/data/tactiq/counter
}

SYSTEMD_SERVICE:${PN} = "tactiq-agent.service"
SYSTEMD_AUTO_ENABLE = "enable"

RDEPENDS:${PN} = "ca-certificates"

FILES:${PN} = " \
    /opt/tactiq/bin/tactiq-agent \
    ${systemd_unitdir}/system/tactiq-agent.service \
    /data/tactiq \
"
