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
SRC_URI += "file://0003-arm64-dts-rk3588s-rock-5a-add-tpm-on-spi4-uboot.patch \
            file://0004-spi-rockchip-add-support-for-cs-gpios.patch"
SRC_URI += "file://env-mmc.cfg"
SRC_URI += "file://boot-ab.cfg"
SRC_URI += "file://env-lockdown.cfg"
SRC_URI += "file://fit-signature.cfg"
SRC_URI += "file://tpm-spi.cfg"
SRC_URI += "file://tactiq-boot.env"

TACTIQ_MIRROR ?= "https://github.com/revenue7-eng/tactiq-os/releases/download/bsp-mirror-2024.10/"

S = "${UNPACKDIR}/u-boot-rockchip-8cdf606e616baa36751f3b4adcfaefc781126c8c"
B = "${WORKDIR}/build"

DEPENDS = "vim-native rkbin-native bc-native dtc-native flex-native bison-native \
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
    ${S}/scripts/kconfig/merge_config.sh -O ${B} -m ${B}/.config ${UNPACKDIR}/env-mmc.cfg ${UNPACKDIR}/boot-ab.cfg ${UNPACKDIR}/env-lockdown.cfg ${UNPACKDIR}/fit-signature.cfg ${UNPACKDIR}/tpm-spi.cfg
    cp ${UNPACKDIR}/tactiq-boot.env ${S}/tactiq-boot.env
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

# --- FIT verification key in U-Boot control FDT ---
# Target established by reading dts/.dt.dtb.cmd: binman takes @fdt-SEQ inputs
# from -I $(dt_dir) per of-list, not from -d (the assembly description).
# u-boot.dtb is NOT the target. A pristine copy of the control FDT is kept so
# key insertion is idempotent and a key-name change cannot leave a stale
# required key in the image (all required keys must verify => stale key
# bricks boot). Known limit: if the source .dts is ever edited, the pristine
# copy goes stale and must be removed by hand (or cleansstate).
TACTIQ_FIT_KEY_DIR  ??= ""
TACTIQ_FIT_KEY_NAME ??= "dev-fit"
TACTIQ_FIT_KEY_REQUIRE ??= "conf"
TACTIQ_FIT_CONTROL_DTB ??= "${B}/dts/upstream/src/arm64/rockchip/rk3588s-rock-5a.dtb"

do_compile:append() {
    # Two dangerous states, both keyed off the boot method: a key in the control
    # FDT is only consulted when U-Boot actually boots a FIT.
    if [ "${TACTIQ_BOOT_METHOD}" = "fit" ]; then
        [ -n "${TACTIQ_FIT_KEY_DIR}" ] || \
            bbfatal "TACTIQ_BOOT_METHOD=fit but TACTIQ_FIT_KEY_DIR is empty: U-Boot would boot a FIT kernel it cannot verify"
        [ "${TACTIQ_FIT_SIGN_KERNEL}" = "1" ] || \
            bbfatal "TACTIQ_BOOT_METHOD=fit with a verification key in the control FDT, but TACTIQ_FIT_SIGN_KERNEL=0: the kernel FIT would be unsigned and the board would not boot"
        [ "${FIT_KERNEL_SIGN_KEYNAME}" = "${TACTIQ_FIT_KEY_NAME}" ] || \
            bbfatal "key name mismatch: control FDT gets '${TACTIQ_FIT_KEY_NAME}', kernel FIT is signed with '${FIT_KERNEL_SIGN_KEYNAME}'"
    fi
    if [ -z "${TACTIQ_FIT_KEY_DIR}" ]; then
        bbwarn "TACTIQ_FIT_KEY_DIR is not set - u-boot.itb has no FIT verification key"
        return
    fi
    [ -f "${TACTIQ_FIT_KEY_DIR}/${TACTIQ_FIT_KEY_NAME}.crt" ] || \
        bbfatal "certificate not found: ${TACTIQ_FIT_KEY_DIR}/${TACTIQ_FIT_KEY_NAME}.crt"
    [ -x "${B}/tools/fdt_add_pubkey" ] || bbfatal "tools/fdt_add_pubkey not built"
    [ -f "${TACTIQ_FIT_CONTROL_DTB}" ] || bbfatal "control FDT not found: ${TACTIQ_FIT_CONTROL_DTB}"

    # Keep/restore pristine control FDT: exactly one key, exactly the current one.
    if [ ! -f "${TACTIQ_FIT_CONTROL_DTB}.pristine" ]; then
        cp "${TACTIQ_FIT_CONTROL_DTB}" "${TACTIQ_FIT_CONTROL_DTB}.pristine"
    fi
    cp "${TACTIQ_FIT_CONTROL_DTB}.pristine" "${TACTIQ_FIT_CONTROL_DTB}"

    "${B}/tools/fdt_add_pubkey" -a sha256,rsa2048 \
        -k "${TACTIQ_FIT_KEY_DIR}" -n "${TACTIQ_FIT_KEY_NAME}" \
        -r "${TACTIQ_FIT_KEY_REQUIRE}" "${TACTIQ_FIT_CONTROL_DTB}"
    grep -qa "key-${TACTIQ_FIT_KEY_NAME}" "${TACTIQ_FIT_CONTROL_DTB}" || \
        bbfatal "fdt_add_pubkey reported success but key is absent in control FDT"

    oe_runmake -C ${S} O=${B}

    grep -qa "key-${TACTIQ_FIT_KEY_NAME}" "${B}/u-boot.itb" || \
        bbfatal "key did not reach u-boot.itb after repack"
}
