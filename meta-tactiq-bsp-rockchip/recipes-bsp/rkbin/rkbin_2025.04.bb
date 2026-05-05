SUMMARY = "Rockchip proprietary binary blobs (DDR init, BL31 ATF)"
DESCRIPTION = "Snapshot of rockchip-linux/rkbin at commit 31a78b07 (2025-04-25). \
Provides DDR initialization blobs and ARM Trusted Firmware binaries required \
to build a bootable U-Boot for RK35xx SoCs. Distributed under Rockchip's \
proprietary license — see LICENSE file inside the archive."

# rkbin upstream has no SPDX license file; the README is the de-facto license.
# Mark explicitly as proprietary so SBOM tooling flags it correctly and
# downstream consumers know this is non-redistributable beyond Rockchip terms.
LICENSE = "Proprietary"
LIC_FILES_CHKSUM = "file://LICENSE;md5=11e3673115959bf596feaaa6ea7ce9a5"

# Pinned to commit 31a78b07f8a2f51a02655efcdda0f3ad30d172b9 (2025-04-25).
# This snapshot includes rk3588_bl31_v1.51.elf and
# rk3588_ddr_lp4_2112MHz_lp5_2400MHz_v1.19.bin used by tactiq-rock5a.
SRC_URI = "${TACTIQ_MIRROR}/rkbin-31a78b07.tar.gz"
SRC_URI[sha256sum] = "869b4c4850b65868d297785b881e1b2f55088c68feb5470a176e1e921725ca3b"

# Set this in your local.conf or distro config to point at the mirror that
# hosts the pinned tarball. For air-gapped / geo-blocked builds, use:
#   TACTIQ_MIRROR = "file:///mnt/c/Users/UserHome/Downloads"
TACTIQ_MIRROR ?= "file:///mnt/c/Users/UserHome/Downloads"

S = "${WORKDIR}/rkbin-31a78b07"

# This recipe ships binary firmware only — no compile, no host arch dependency.
INHIBIT_DEFAULT_DEPS = "1"
INHIBIT_PACKAGE_STRIP = "1"
INHIBIT_PACKAGE_DEBUG_SPLIT = "1"
INSANE_SKIP:${PN} += "arch already-stripped"

COMPATIBLE_HOST = ".*-linux"
PACKAGE_ARCH = "${MACHINE_ARCH}"

do_configure[noexec] = "1"
do_compile[noexec] = "1"

do_install() {
    install -d ${D}${datadir}/rkbin/bin/rk35
    # Install only the blobs we actually use for tactiq-rock5a.
    # Adding more boards later means adding more lines here, deliberately —
    # we do NOT bulk-copy bin/ to keep provenance surface minimal.
    install -m 0644 ${S}/bin/rk35/rk3588_ddr_lp4_2112MHz_lp5_2400MHz_v1.19.bin \
        ${D}${datadir}/rkbin/bin/rk35/
    install -m 0644 ${S}/bin/rk35/rk3588_bl31_v1.51.elf \
        ${D}${datadir}/rkbin/bin/rk35/
}

# Expose the install paths to other recipes (u-boot-rockchip consumes them).
SYSROOT_DIRS += "${datadir}/rkbin"

FILES:${PN} = "${datadir}/rkbin"
BBCLASSEXTEND = "native"
