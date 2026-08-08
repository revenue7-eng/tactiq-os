SUMMARY = "TactiQ OS — agentgateway static configuration"
DESCRIPTION = "Production config.yaml for the in-perimeter agentgateway MCP \
mediator. Shipped as a standalone package, separate from the agentgateway \
binary, so the configuration is measured by IMA independently of the binary."
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "file://config.yaml"

UNPACKDIR = "${WORKDIR}/sources"
# config.yaml unpacks directly into UNPACKDIR (no ${BP} subdir for a bare
# file:// fetch). Point S there so bitbake doesn't warn about a missing
# ${UNPACKDIR}/${BP} source dir.
S = "${UNPACKDIR}"

do_install() {
    install -d ${D}/etc/tactiq/agentgateway
    install -m 0644 ${UNPACKDIR}/config.yaml ${D}/etc/tactiq/agentgateway/config.yaml
}

# Own only the agentgateway sub-tree, NOT /etc/tactiq itself (tactiq-config
# owns that). Separate sub-trees => no directory-ownership conflict.
FILES:${PN} = "/etc/tactiq/agentgateway"

CONFFILES:${PN} = "/etc/tactiq/agentgateway/config.yaml"

# No systemd unit here on purpose: the agentgateway.service unit ships with
# the binary package. Keeping this recipe config-only yields a clean,
# independent IMA measurement of the configuration.
