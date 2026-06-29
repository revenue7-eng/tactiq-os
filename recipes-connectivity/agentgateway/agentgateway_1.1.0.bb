SUMMARY = "agentgateway data plane for in-perimeter MCP/A2A traffic mediation"
DESCRIPTION = "agentgateway Rust data plane, built without the web UI and without \
the Go control-plane. Runs in static local-config mode to mediate MCP traffic \
between local agents and local tools. Does not expose user-facing network services."
HOMEPAGE = "https://github.com/agentgateway/agentgateway"
LICENSE = "Apache-2.0"
LIC_FILES_CHKSUM = "file://LICENSE;md5=3154c08acdebeb3272f2707a68139d01"

PV = "1.1.0"
SRCREV = "d204f9ce1ac785d4b23145cce64c4a34a5c540c9"
SRC_URI = "git://github.com/agentgateway/agentgateway.git;protocol=https;branch=main"

# Build target ships Rust 1.94.x; edition 2024 (needs >= 1.85) is satisfied.
# Upstream rust-toolchain.toml pins 1.96 but is not honoured under bitbake.

inherit cargo systemd useradd

# Pre-vendored sources mounted from the premirror; no per-crate fetch at build.
# Override TACTIQ_VENDOR_DIR in local.conf if the mirror lives elsewhere.
TACTIQ_VENDOR_DIR ?= "${DL_DIR}/agentgateway-vendor-${PV}"
CARGO_DISABLE_BITBAKE_VENDORING = "1"

# Unprivileged system user for the service (no home, no shell).
USERADD_PACKAGES = "${PN}"
USERADD_PARAM:${PN} = "--system --no-create-home --shell /sbin/nologin --user-group agentgateway"
GROUPADD_PARAM:${PN} = "--system agentgateway"

do_configure:prepend() {
    mkdir -p ${S}/.cargo
    cat >> ${S}/.cargo/config.toml << CARGOEOF
[source.crates-io]
replace-with = "vendored-sources"
[source.vendored-sources]
directory = "${TACTIQ_VENDOR_DIR}"
CARGOEOF
}

# aws-lc-sys (tls-aws-lc) needs cmake. openssl is gated behind tls-openssl and
# is not built in this feature set, so it is intentionally absent from DEPENDS.
DEPENDS += "cmake-native"

CARGO_BUILD_FLAGS += " --bin agentgateway --no-default-features --features tls-aws-lc"

RUSTFLAGS += "--remap-path-prefix=${WORKDIR}=/usr/src/debug/${PN}/${PV}"
export SOURCE_DATE_EPOCH

SYSTEMD_SERVICE:${PN} = "agentgateway.service"
SYSTEMD_AUTO_ENABLE = "disable"
SRC_URI += "file://agentgateway.service"

do_install:append() {
    install -d ${D}/opt/tactiq/bin
    install -m 0755 ${B}/target/${CARGO_TARGET_SUBDIR}/agentgateway ${D}/opt/tactiq/bin/agentgateway
    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${WORKDIR}/agentgateway.service ${D}${systemd_system_unitdir}/
}

FILES:${PN} = "/opt/tactiq/bin/agentgateway ${systemd_system_unitdir}/agentgateway.service"
