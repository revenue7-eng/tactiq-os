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

# Vendored crate tree. Three dependencies come from git forks (http-serde,
# schemars, wiremock-rs), and cargo-update-recipe-crates only emits crate://
# entries for packages whose Cargo.lock source contains "crates.io" -- so those
# three cannot be expressed that way and this recipe builds from a vendored
# tree instead.
#
# The tree is a function of SRCREV alone: `cargo vendor --locked` at this
# commit is byte-for-byte reproducible (verified by generating it twice, the
# second time with the cargo registry cache cleared, and comparing with
# diff -r across 727 crates: no differences). scripts/vendor-agentgateway.sh
# regenerates it and checks the result against a recorded hash, so a clean
# machine can produce the same tree rather than needing one copied to it.
CARGO_VENDORING_DIRECTORY ?= "${DL_DIR}/agentgateway-vendor-${PV}"

# Fail early and legibly. Without this the build gets as far as do_compile and
# dies inside cargo with "failed to read root of directory source", which says
# nothing about what to do next.
do_configure[prefuncs] += "agentgateway_check_vendor"
agentgateway_check_vendor() {
    if [ ! -d "${CARGO_VENDORING_DIRECTORY}" ]; then
        bbfatal "vendored crate tree missing: ${CARGO_VENDORING_DIRECTORY}\n\
Generate it with:\n\
\n\
    <tactiq-os>/scripts/vendor-agentgateway.sh ${DL_DIR}\n\
\n\
It is regenerated from SRCREV ${SRCREV} and checked against a recorded\n\
hash; it is not something to be copied between machines by hand."
    fi
}

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
