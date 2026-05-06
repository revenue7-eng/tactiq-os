SUMMARY = "Rockchip proprietary binary blobs (DDR init, BL31 ATF)"
DESCRIPTION = "Snapshot of rockchip-linux/rkbin at commit 7c35e21a (2024-10). \
This is the same commit pinned by meta-rockchip's rockchip-rkbin recipe and \
verified compatible with U-Boot 2024.01 mainline on RK3588S (Rock 5A boot \
verified 2026-05-04). \
Provides DDR initialization blobs and ARM Trusted Firmware binaries required \
to build a bootable U-Boot for RK35xx SoCs. Distributed under Rockchip's \
proprietary license — see LICENSE file inside the archive."

LICENSE = "Proprietary"
LIC_FILES_CHKSUM = "file://LICENSE;md5=11e3673115959bf596feaaa6ea7ce9a5"

# Pinned to commit 7c35e21a8529b3758d1f051d1a5dc62aae934b2b.
# This snapshot includes rk3588_bl31_v1.47.elf and
# rk3588_ddr_lp4_2112MHz_lp5_2400MHz_v1.18.bin used by tactiq-rock5a.
SRC_URI = "${TACTIQ_MIRROR}/rkbin-7c35e21a.tar.gz"
SRC_URI[sha256sum] = "18bde6ce71df308197db0e1d95fd73a19b6a32f4f0b6f5567333ef3c5b617452"

TACTIQ_MIRROR ?= "file:///mnt/c/Users/UserHome/Downloads"

S = "${WORKDIR}/rkbin-7c35e21a8529b3758d1f051d1a5dc62aae934b2b"

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
    install -m 0644 ${S}/bin/rk35/rk3588_ddr_lp4_2112MHz_lp5_2400MHz_v1.18.bin \
        ${D}${datadir}/rkbin/bin/rk35/
    install -m 0644 ${S}/bin/rk35/rk3588_bl31_v1.47.elf \
        ${D}${datadir}/rkbin/bin/rk35/
}

SYSROOT_DIRS += "${datadir}/rkbin"
FILES:${PN} = "${datadir}/rkbin"
BBCLASSEXTEND = "native"
