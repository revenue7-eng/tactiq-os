SUMMARY = "TactiQ OS reference tool and reference agent for the tool boundary"
DESCRIPTION = "Two small programs for the development image. tactiq-reftool \
is an MCP server on stdio with one tool, valve_status, that returns a fixed \
answer; agentgateway starts it as a child process, as agentgateway-config \
requires of every tool. tactiq-refagent tries to run the tool itself and to \
connect around the gateway, which its SELinux domain must refuse, and then \
calls the tool through agentgateway. Together they show the tool boundary of \
the policy acting on the board."
HOMEPAGE = "https://github.com/revenue7-eng/tactiq-os"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"
SPDX_PACKAGE_SUPPLIER_ref = "SPDX_SUPPLIER_tactiq"

SRC_URI = "file://tactiq-reftool.c \
           file://tactiq-refagent.c \
           file://tactiq-refagent.service \
          "

UNPACKDIR = "${WORKDIR}/sources"
S = "${UNPACKDIR}"

do_compile() {
    for p in tactiq-reftool tactiq-refagent; do
        ${CC} ${CFLAGS} ${LDFLAGS} -std=c11 -D_GNU_SOURCE -Wall -Wextra -Werror \
            -o ${B}/$p ${S}/$p.c
    done
}

do_install() {
    install -d ${D}/opt/tactiq/bin
    install -m 0755 ${B}/tactiq-reftool ${D}/opt/tactiq/bin/tactiq-reftool
    install -m 0755 ${B}/tactiq-refagent ${D}/opt/tactiq/bin/tactiq-refagent
    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${S}/tactiq-refagent.service ${D}${systemd_system_unitdir}/
}

# The tool has no unit: agentgateway starts it. The agent is run by hand
# (systemctl start tactiq-refagent) and has no [Install] section, so the
# systemd class, which enables units, is not used.
FILES:${PN} += "/opt/tactiq/bin ${systemd_system_unitdir}/tactiq-refagent.service"

# The gateway starts the tool and the agent calls it; without the gateway
# neither has anything to do.
RDEPENDS:${PN} = "agentgateway agentgateway-config"
