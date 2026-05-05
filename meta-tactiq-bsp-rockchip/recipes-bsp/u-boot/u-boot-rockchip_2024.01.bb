SUMMARY = "U-Boot bootloader for Rockchip RK35xx, packed with rkbin blobs"
DESCRIPTION = "Builds mainline U-Boot 2024.01 for Rockchip RK35xx targets \
(currently tactiq-rock5a) and packs the resulting SPL with the proprietary \
DDR initialization blob (idbloader.img) and the U-Boot proper with ARM \
Trusted Firmware as a FIT image (u-boot.itb). \
Source: https://ftp.denx.de/pub/u-boot/u-boot-2024.01.tar.bz2"

LICENSE = "GPL-2.0-or-later"
LIC_FILES_CHKSUM = "file://Licenses/README;md5=2ca5f2c35c8cc335f0a19756634782f1"

# Pinned upstream tarball — denx.de is the canonical U-Boot mirror.
# sha256 verified against b99611f1ed237bf3541bdc8434b68c96a6e05967061f992443cb30aabebef5b3
SRC_URI = "${TACTIQ_MIRROR}/u-boot-2024.01.tar.bz2"
SRC_URI[sha256sum] = "b99611f1ed237bf3541bdc8434b68c96a6e05967061f992443cb30aabebef5b3"

TACTIQ_MIRROR ?= "file:///mnt/c/Users/UserHome/Downloads"

S = "${WORKDIR}/u-boot-2024.01"
B = "${WORKDIR}/build"

# rkbin recipe stages blobs into ${STAGING_DATADIR_NATIVE}/rkbin/bin/rk35/
DEPENDS = "rkbin-native bc-native dtc-native flex-native bison-native \
           openssl-native python3-pyelftools-native swig-native"

# Inherit poky's standard classes:
#  - kernel-arch: auto-derives ARCH (e.g. arm for arm64 targets — U-Boot's
#    source tree uses arch/arm/ for both 32-bit and 64-bit ARM)
#  - deploy: enables do_deploy task
#  - python3native: tools/binman is python3
inherit kernel-arch deploy python3native

# Mirrors poky's recipes-bsp/u-boot/u-boot.inc EXTRA_OEMAKE pattern.
# CC line includes TOOLCHAIN_OPTIONS which carries --sysroot and the path
# to target libgcc (resolves "cannot find -lgcc" at link time).
# HOSTCC line bundles BUILD_CFLAGS/BUILD_LDFLAGS so host tools find
# openssl headers/libs from recipe-sysroot-native.
EXTRA_OEMAKE = 'CROSS_COMPILE=${TARGET_PREFIX} \
                CC="${TARGET_PREFIX}gcc ${TOOLCHAIN_OPTIONS} ${DEBUG_PREFIX_MAP}" \
                V=1'
EXTRA_OEMAKE += 'HOSTCC="${BUILD_CC} ${BUILD_CFLAGS} ${BUILD_LDFLAGS}" \
                 HOSTSTRIP=true'
EXTRA_OEMAKE += 'STAGING_INCDIR=${STAGING_INCDIR_NATIVE} \
                 STAGING_LIBDIR=${STAGING_LIBDIR_NATIVE}'
# Rockchip-specific blobs from the rkbin-native recipe.
EXTRA_OEMAKE += 'BL31=${STAGING_DATADIR_NATIVE}/rkbin/bin/rk35/rk3588_bl31_v1.51.elf \
                 ROCKCHIP_TPL=${STAGING_DATADIR_NATIVE}/rkbin/bin/rk35/rk3588_ddr_lp4_2112MHz_lp5_2400MHz_v1.19.bin'

# UBOOT_MACHINE comes from the machine config (e.g. tactiq-rock5a.conf
# sets UBOOT_MACHINE = "rock5a-rk3588s_defconfig").
UBOOT_MACHINE ??= ""

python () {
    if not d.getVar("UBOOT_MACHINE"):
        bb.fatal("UBOOT_MACHINE is not set — set it in the machine config "
                 "(e.g. UBOOT_MACHINE = \"rock5a-rk3588s_defconfig\")")
}

do_configure() {
    oe_runmake -C ${S} O=${B} ${UBOOT_MACHINE}
}

do_compile() {
    unset LDFLAGS
    oe_runmake -C ${S} O=${B}
}

# Stage the two artefacts wic consumes via WKS_FILE rawcopy entries.
# IMAGE_BOOT_FILES picks them up from DEPLOY_DIR_IMAGE.
do_deploy() {
    install -d ${DEPLOYDIR}
    install -m 0644 ${B}/idbloader.img ${DEPLOYDIR}/idbloader.img
    install -m 0644 ${B}/u-boot.itb    ${DEPLOYDIR}/u-boot.itb
}

addtask deploy after do_compile before do_build

# This recipe produces deployable artefacts only — no target packages.
do_install[noexec] = "1"
deltask do_install
deltask do_populate_sysroot

# Provide an alias so machine configs / images can depend on the generic name.
PROVIDES = "virtual/bootloader u-boot"
