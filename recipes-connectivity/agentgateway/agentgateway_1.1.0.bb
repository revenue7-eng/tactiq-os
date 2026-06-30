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

# Pre-vendored sources from the premirror; no per-crate fetch at build.
# Point the class vendoring mechanism at our cargo-vendor tree. The class
# writes [source.bitbake] -> CARGO_VENDORING_DIRECTORY into the real cargo
# config (${CARGO_HOME}/config.toml). Override in local.conf if the mirror
# lives elsewhere.
CARGO_VENDORING_DIRECTORY ?= "${DL_DIR}/agentgateway-vendor-${PV}"

# Unprivileged system user for the service (no home, no shell).
USERADD_PACKAGES = "${PN}"
USERADD_PARAM:${PN} = "--system --no-create-home --shell /sbin/nologin --gid agentgateway agentgateway"
GROUPADD_PARAM:${PN} = "--system agentgateway"

# The cargo_common class writes the base config (incl. [source.bitbake] ->
# CARGO_VENDORING_DIRECTORY) into ${CARGO_HOME}/config.toml during
# do_configure, including [source.crates-io] -> bitbake. We only need to add
# the three git-fork redirects to that same file, pointing at 'bitbake' too.
do_configure:append() {
    cat >> ${CARGO_HOME}/config.toml << CARGOEOF
[source."git+https://gitlab.com/howardjohn/http-serde?rev=163f20f551c2cf6032254b6dbbe246b91ce727ad"]
git = "https://gitlab.com/howardjohn/http-serde"
rev = "163f20f551c2cf6032254b6dbbe246b91ce727ad"
replace-with = "bitbake"
[source."git+https://github.com/howardjohn/schemars?rev=4364354fa41897a0c2001d891c0a9a38eafedb82"]
git = "https://github.com/howardjohn/schemars"
rev = "4364354fa41897a0c2001d891c0a9a38eafedb82"
replace-with = "bitbake"
[source."git+https://github.com/howardjohn/wiremock-rs?rev=e55f5b96083125fdabc3e62f92790ee15ae3a10d"]
git = "https://github.com/howardjohn/wiremock-rs"
rev = "e55f5b96083125fdabc3e62f92790ee15ae3a10d"
replace-with = "bitbake"
CARGOEOF
}

# TLS provider (aws-lc-rs) is wired via rustls deps, not a cargo feature — the
# project has no tls-* features in v1.1.0. cmake-native builds aws-lc-sys,
# pulled in transitively via aws-lc-rs.
DEPENDS += "cmake-native"

CARGO_BUILD_FLAGS += " --bin agentgateway"

# tokio is pulled with the taskdump feature, which hard-requires
# --cfg tokio_unstable. Upstream sets this in the project .cargo/config.toml,
# but bitbake reads CARGO_HOME, so set it via RUSTFLAGS here.
RUSTFLAGS += "--remap-path-prefix=${WORKDIR}=/usr/src/debug/${PN}/${PV} --cfg tokio_unstable"
export SOURCE_DATE_EPOCH

SYSTEMD_SERVICE:${PN} = "agentgateway.service"
SYSTEMD_AUTO_ENABLE = "disable"
SRC_URI += "file://agentgateway.service"

do_install:append() {
    install -d ${D}/opt/tactiq/bin
    install -m 0755 ${B}/target/${CARGO_TARGET_SUBDIR}/agentgateway ${D}/opt/tactiq/bin/agentgateway
    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${UNPACKDIR}/agentgateway.service ${D}${systemd_system_unitdir}/
    rm -rf ${D}${bindir}
}

FILES:${PN} = "/opt/tactiq/bin/agentgateway ${systemd_system_unitdir}/agentgateway.service"
