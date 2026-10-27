SUMMARY = "TactiQ agent stop service"
DESCRIPTION = "Answers agentgateway's extAuthz question before every tool \
call, on 127.0.0.1:49318. The stop state is the parity of a TPM NV counter \
(odd = stopped); a refusal carries a receipt with the TPM's own NV_Certify of \
that counter and an AK quote over the boot PCRs, which the service checks \
before handing it out."
HOMEPAGE = "https://github.com/revenue7-eng/tactiq-attest"
LICENSE = "Apache-2.0"
LIC_FILES_CHKSUM = "file://LICENSE;md5=3b83ef96387f14655fc854ddc3c6bd57"
SPDX_PACKAGE_SUPPLIER_ref = "SPDX_SUPPLIER_tactiq"

# Same repository and revision as tactiq-agent: the stop service shares the
# envelope, the TPM layer and the AK with it, so the two are built from one
# tree. Keep the two SRCREVs equal.
SRCREV = "d3a561d9222759c6a50def7872fdf4edb8b461f8"
SRC_URI = "git://github.com/revenue7-eng/tactiq-attest.git;protocol=https;branch=main"
SRC_URI += "file://tactiq-stop.service file://tactiq-stop.tmpfiles"

# The workspace's crate list is shared with tactiq-agent: one Cargo.lock,
# and the stop service adds no crates.io dependency of its own (sha2 is
# already there for the envelope).
require tactiq-agent-crates.inc

inherit cargo cargo-update-recipe-crates systemd

# Only the stop service, and only its dependency tree (see the -p note in
# tactiq-agent_0.1.1.bb for why -p matters with this workspace).
CARGO_BUILD_FLAGS += "-p stop --bin tactiq-stop"

RUSTFLAGS += "--remap-path-prefix=${WORKDIR}=/usr/src/debug/${PN}/${PV}"
export SOURCE_DATE_EPOCH

# The service reaches the TPM through tpm2-tools, as the agent does.
# It reads the gateway config at start, but does not depend on its package:
# the dependency runs the other way (agentgateway-config requires this
# service), and a cycle would hide which one needs which. Without the config
# the service refuses to start, and the gateway, if any, denies every call.
RDEPENDS:${PN} = "tpm2-tools libtss2 libtss2-mu libtss2-tcti-device tactiq-agent"

SYSTEMD_SERVICE:${PN} = "tactiq-stop.service"
# Enabled: the service refuses to start until the stop counter exists
# (`tactiq-stop define`) and the gateway config carries the extAuthz block it
# requires, and while it is down the gateway denies every tool call.
SYSTEMD_AUTO_ENABLE = "enable"

do_install:append() {
    install -d ${D}/opt/tactiq/bin
    install -m 0755 ${B}/target/${CARGO_TARGET_SUBDIR}/tactiq-stop ${D}/opt/tactiq/bin/tactiq-stop
    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${UNPACKDIR}/tactiq-stop.service ${D}${systemd_system_unitdir}/
    install -d ${D}${nonarch_libdir}/tmpfiles.d
    install -m 0644 ${UNPACKDIR}/tactiq-stop.tmpfiles ${D}${nonarch_libdir}/tmpfiles.d/tactiq-stop.conf
    rm -rf ${D}${bindir}
}

FILES:${PN} = " \
    /opt/tactiq/bin/tactiq-stop \
    ${systemd_system_unitdir}/tactiq-stop.service \
    ${nonarch_libdir}/tmpfiles.d/tactiq-stop.conf \
"
