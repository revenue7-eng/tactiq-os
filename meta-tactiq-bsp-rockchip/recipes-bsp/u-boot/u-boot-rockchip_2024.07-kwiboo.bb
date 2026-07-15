SUMMARY = "U-Boot bootloader for Rockchip RK35xx (Kwiboo fork)"
DESCRIPTION = "Builds Kwiboo's U-Boot fork (rk3xxx-2024.07 branch) for Rockchip \
RK35xx targets. This fork contains RK3588 patches not yet merged into mainline. \
Same commit (8cdf606e) used by meta-rockchip bbappend for RK3588 boards. \
Pure mainline u-boot does not boot on RK3588 family — see Gentoo wiki, yrzr blog. \
Source: https://github.com/Kwiboo/u-boot-rockchip/tree/rk3xxx-2024.07"

LICENSE = "GPL-2.0-or-later"
LIC_FILES_CHKSUM = "file://Licenses/README;md5=2ca5f2c35c8cc335f0a19756634782f1"

# Pinned to Kwiboo commit 8cdf606e616baa36751f3b4adcfaefc781126c8c (rk3xxx-2024.07).
SRC_URI = "${TACTIQ_MIRROR}/u-boot-rockchip-8cdf606e616baa36751f3b4adcfaefc781126c8c.tar.gz"
SRC_URI[sha256sum] = "b6fc46e29457003d86041c299d15bde9dfc6597643d6cd303d4b6925772b24c8"

# wrynose ships swig-native 4.3: SWIG_Python_AppendOutput() grew a third
# is_void argument; pylibfdt typemaps still use the 2-arg call (FTBFS).
# Backport of the upstream dtc approach (SWIG_AppendOutput macro).
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI += "file://0001-pylibfdt-swig-4.3-compat.patch"
SRC_URI += "file://0002-binman-drop-pkg-resources.patch"
SRC_URI += "file://env-mmc.cfg"

TACTIQ_MIRROR ?= "file:///mnt/c/Users/UserHome/Downloads"

S = "${UNPACKDIR}/u-boot-rockchip-8cdf606e616baa36751f3b4adcfaefc781126c8c"
B = "${WORKDIR}/build"

DEPENDS = "rkbin-native bc-native dtc-native flex-native bison-native \
           openssl-native python3-pyelftools-native swig-native"

inherit kernel-arch deploy python3native

EXTRA_OEMAKE = 'CROSS_COMPILE=${TARGET_PREFIX} \
                CC="${TARGET_PREFIX}gcc ${TOOLCHAIN_OPTIONS} ${DEBUG_PREFIX_MAP}" \
                V=1'
EXTRA_OEMAKE += 'HOSTCC="${BUILD_CC} ${BUILD_CFLAGS} ${BUILD_LDFLAGS}" \
                 HOSTSTRIP=true'
EXTRA_OEMAKE += 'STAGING_INCDIR=${STAGING_INCDIR_NATIVE} \
                 STAGING_LIBDIR=${STAGING_LIBDIR_NATIVE}'
EXTRA_OEMAKE += 'BL31=${STAGING_DATADIR_NATIVE}/rkbin/bin/rk35/rk3588_bl31_v1.47.elf \
                 ROCKCHIP_TPL=${STAGING_DATADIR_NATIVE}/rkbin/bin/rk35/rk3588_ddr_lp4_2112MHz_lp5_2400MHz_v1.18.bin'

UBOOT_MACHINE ??= ""

python () {
    if not d.getVar("UBOOT_MACHINE"):
        bb.fatal("UBOOT_MACHINE is not set — set it in the machine config "
                 "(e.g. UBOOT_MACHINE = \"rock5a-rk3588s_defconfig\")")
}

do_configure() {
    oe_runmake -C ${S} O=${B} ${UBOOT_MACHINE}
    ${S}/scripts/kconfig/merge_config.sh -O ${B} -m ${B}/.config ${UNPACKDIR}/env-mmc.cfg
    oe_runmake -C ${S} O=${B} olddefconfig
}

do_compile() {
    unset LDFLAGS
    oe_runmake -C ${S} O=${B}
    oe_runmake -C ${S} O=${B} u-boot-initial-env
}

do_deploy() {
    install -d ${DEPLOYDIR}
    install -m 0644 ${B}/idbloader.img ${DEPLOYDIR}/idbloader.img
    install -m 0644 ${B}/u-boot.itb    ${DEPLOYDIR}/u-boot.itb
    install -m 0644 ${B}/u-boot-initial-env ${DEPLOYDIR}/u-boot-initial-env
}

addtask deploy after do_compile before do_build

do_install[noexec] = "1"
deltask do_install
deltask do_populate_sysroot

PROVIDES = "virtual/bootloader u-boot"
