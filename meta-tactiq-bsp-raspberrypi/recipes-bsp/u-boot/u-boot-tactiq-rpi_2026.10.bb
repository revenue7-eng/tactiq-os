SUMMARY = "U-Boot bootloader for the Raspberry Pi 4 (mainline v2026.10)"
DESCRIPTION = "Builds mainline U-Boot v2026.10 for the Raspberry Pi 4 Model B \
from the same source archive as u-boot-rockchip_2026.10.bb, with the same \
board-independent patches and the same lockdown fragments. The VideoCore \
firmware loads the result (u-boot.bin) as kernel8.img."

HOMEPAGE = "https://u-boot.org"
LICENSE = "GPL-2.0-or-later"
LIC_FILES_CHKSUM = "file://Licenses/README;md5=2ca5f2c35c8cc335f0a19756634782f1"

# Stage 3 of the track "own root, own board": boots the signed FIT, without a
# TPM and without measured boot. Not yet booted on a board.

# Release tag v2026.10 (commit 5508406582f6f7120dce0c4b3059819a41788db2),
# GitHub archive of the tag, mirrored like the other BSP sources. Same
# archive and checksum as the Rockchip recipe.
SRC_URI = "${TACTIQ_MIRROR}/u-boot-v2026.10.tar.gz"
SRC_URI[sha256sum] = "f943a88389c8fd70a6b0d061a88267465e143c7ca6ea2b75837ab20f5b60c739"
TACTIQ_MIRROR ?= "https://github.com/revenue7-eng/tactiq-os/releases/download/bsp-mirror-2024.10/"

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

# 0001: U-Boot's build refuses OF_BOARD off on a board that implies
# OF_HAS_PRIOR_STAGE (scripts/check-of.sh) unless the board is on an
# allowlist; rpi4.cfg turns OF_BOARD off, see there for why.
# 0002: U-Boot's own tree has no mmc aliases, so "mmc 0" would follow bind
# order, where the Wi-Fi SDIO controller comes first; pin mmc0 to the SD
# card (checked after the build below).
SRC_URI += "file://0001-scripts-allow-rpi-to-build-without-OF_BOARD.patch \
            file://0002-arm-dts-bcm2711-rpi-4-b-pin-mmc0-to-the-SD-card.patch"

# Copies of the Rockchip layer's fragments (byte-identical, checked by
# tests/bsp/test_bsp_shared_files.py): boot-ab, env-lockdown, fit-signature,
# net-off, console-lockdown, tools. Pi-specific: env-mmc, rpi4, and the
# default environment with the Pi partition numbers.
SRC_URI += "file://env-mmc.cfg \
            file://boot-ab.cfg \
            file://env-lockdown.cfg \
            file://fit-signature.cfg \
            file://tools.cfg \
            file://net-off.cfg \
            file://console-lockdown.cfg \
            file://rpi4.cfg \
            file://tactiq-boot-fit.env"

# Only the FIT path exists on this board: there is no extlinux variant of the
# Pi environment.
python () {
    if d.getVar('TACTIQ_BOOT_METHOD') != 'fit':
        bb.fatal("u-boot-tactiq-rpi supports TACTIQ_BOOT_METHOD = \"fit\" only, got '%s'"
                 % d.getVar('TACTIQ_BOOT_METHOD'))
}

# FIT configuration names follow kernel-fit-image (conf-<dtb basename>) and
# the per-slot devicetrees of tactiq-slot-dtb.bb (slot B adds "-b").
TACTIQ_FIT_DTB = "${@os.path.basename(d.getVar('KERNEL_DEVICETREE').split()[0])}"
do_configure[vardeps] += "TACTIQ_FIT_DTB"

# Interactive U-Boot console, for bench builds only. Off unless a build sets
# it to "1" in its own local.conf. A loader carrying a FIT key other than the
# development key is never built with it (checked in do_configure).
TACTIQ_UBOOT_CONSOLE ??= "0"
do_configure[vardeps] += "TACTIQ_UBOOT_CONSOLE TACTIQ_FIT_KEY_NAME"

S = "${UNPACKDIR}/u-boot-2026.10"
B = "${WORKDIR}/build"

DEPENDS = "vim-native bc-native dtc-native flex-native bison-native \
           openssl-native python3-pyelftools-native swig-native"

inherit kernel-arch deploy python3native

EXTRA_OEMAKE = 'CROSS_COMPILE=${TARGET_PREFIX} \
                CC="${TARGET_PREFIX}gcc ${TOOLCHAIN_OPTIONS} ${DEBUG_PREFIX_MAP}" \
                V=1'
EXTRA_OEMAKE += 'HOSTCC="${BUILD_CC} ${BUILD_CFLAGS} ${BUILD_LDFLAGS}" \
                 HOSTSTRIP=true'
EXTRA_OEMAKE += 'STAGING_INCDIR=${STAGING_INCDIR_NATIVE} \
                 STAGING_LIBDIR=${STAGING_LIBDIR_NATIVE}'

UBOOT_MACHINE ??= ""

python () {
    if not d.getVar("UBOOT_MACHINE"):
        bb.fatal("UBOOT_MACHINE is not set: set it in the machine config "
                 "(UBOOT_MACHINE = \"rpi_4_defconfig\")")
}

do_configure() {
    oe_runmake -C ${S} O=${B} ${UBOOT_MACHINE}
    if [ "${TACTIQ_UBOOT_CONSOLE}" = "1" ] && [ "${TACTIQ_FIT_KEY_NAME}" != "dev-fit" ]; then
        bbfatal "TACTIQ_UBOOT_CONSOLE=1 with FIT key '${TACTIQ_FIT_KEY_NAME}': the console is for development loaders only"
    fi
    lockdown=""
    [ "${TACTIQ_UBOOT_CONSOLE}" = "1" ] || lockdown="${UNPACKDIR}/console-lockdown.cfg"
    ${S}/scripts/kconfig/merge_config.sh -O ${B} -m ${B}/.config ${UNPACKDIR}/env-mmc.cfg ${UNPACKDIR}/boot-ab.cfg ${UNPACKDIR}/env-lockdown.cfg ${UNPACKDIR}/fit-signature.cfg ${UNPACKDIR}/tools.cfg ${UNPACKDIR}/net-off.cfg ${UNPACKDIR}/rpi4.cfg ${lockdown}
    dtb="${TACTIQ_FIT_DTB}"
    sed -e "s|@FIT_CONF_A@|conf-${dtb}|g" -e "s|@FIT_CONF_B@|conf-${dtb%.dtb}-b.dtb|g" \
        ${UNPACKDIR}/tactiq-boot-fit.env > ${S}/tactiq-boot.env
    if grep -q "@FIT_CONF_" ${S}/tactiq-boot.env; then
        bbfatal "unresolved FIT configuration placeholder in tactiq-boot-fit.env"
    fi
    oe_runmake -C ${S} O=${B} olddefconfig
    # olddefconfig drops a symbol with unmet dependencies without a word.
    ! grep -q '^CONFIG_OF_BOARD=y$' ${B}/.config || \
        bbfatal "CONFIG_OF_BOARD is set: U-Boot would take the firmware's devicetree, which has no FIT key"
    grep -q '^CONFIG_OF_SEPARATE=y$' ${B}/.config || \
        bbfatal "CONFIG_OF_SEPARATE is not set: the control devicetree carrying the FIT key is not appended to u-boot.bin"
    ! grep -q '^CONFIG_OF_OMIT_DTB=y$' ${B}/.config || \
        bbfatal "CONFIG_OF_OMIT_DTB is set: u-boot.bin would carry no control devicetree"
    grep -q '^CONFIG_DEFAULT_DEVICE_TREE="bcm2711-rpi-4-b"$' ${B}/.config || \
        bbfatal "CONFIG_DEFAULT_DEVICE_TREE is not bcm2711-rpi-4-b: the FIT key could land in a tree U-Boot does not use"
    grep -q '^CONFIG_FIT_SIGNATURE=y$' ${B}/.config || \
        bbfatal "CONFIG_FIT_SIGNATURE did not survive olddefconfig"
    grep -q '^CONFIG_ENV_IS_IN_MMC=y$' ${B}/.config || \
        bbfatal "CONFIG_ENV_IS_IN_MMC is not set: the A/B state would not be kept in the raw window"
    ! grep -q '^CONFIG_ENV_IS_IN_FAT=y$' ${B}/.config || \
        bbfatal "CONFIG_ENV_IS_IN_FAT is still set: the environment would also be read from the firmware partition"
    grep -q '^CONFIG_ENV_FLAGS_LIST_STATIC="BOOT_ORDER:sw,BOOT_A_LEFT:dw,BOOT_B_LEFT:dw"$' ${B}/.config || \
        bbfatal "CONFIG_ENV_FLAGS_LIST_STATIC is not the A/B list: with ENV_WRITEABLE_LIST nothing would be imported from the saved environment"
    ! grep -q '^CONFIG_NET=y$' ${B}/.config || \
        bbfatal "CONFIG_NET is still set: net-off.cfg did not apply"
    ! grep -q '^CONFIG_USE_PREBOOT=y$' ${B}/.config || \
        bbfatal "CONFIG_USE_PREBOOT is still set: pci enum and usb start would run before boot_ab"
    if [ "${TACTIQ_UBOOT_CONSOLE}" != "1" ]; then
        grep -q '^CONFIG_BOOTDELAY=-2$' ${B}/.config || \
            bbfatal "console lockdown: CONFIG_BOOTDELAY is not -2"
        ! grep -q '^CONFIG_CMD_TPM=y$' ${B}/.config || \
            bbfatal "console lockdown: CONFIG_CMD_TPM is still set"
    fi
}

do_compile() {
    unset LDFLAGS
    oe_runmake -C ${S} O=${B}
    oe_runmake -C ${S} O=${B} u-boot-initial-env
}

# --- FIT verification key in U-Boot control FDT ---
# With OF_SEPARATE the control FDT appended to u-boot.bin is dts/dt.dtb, a
# copy of arch/arm/dts/<CONFIG_DEFAULT_DEVICE_TREE>.dtb. The key is inserted
# into that source tree and make is run again, which copies it into
# dts/dt.dtb and u-boot.dtb and re-concatenates u-boot.bin. A pristine copy
# keeps key insertion idempotent, as in the Rockchip recipe.
TACTIQ_FIT_KEY_DIR  ??= ""
TACTIQ_FIT_KEY_NAME ??= "dev-fit"
TACTIQ_FIT_KEY_REQUIRE ??= "conf"
TACTIQ_FIT_CONTROL_DTB ??= "${B}/arch/arm/dts/bcm2711-rpi-4-b.dtb"

do_compile:append() {
    [ -n "${TACTIQ_FIT_KEY_DIR}" ] || \
        bbfatal "TACTIQ_FIT_KEY_DIR is empty: U-Boot would boot a FIT kernel it cannot verify"
    [ "${TACTIQ_FIT_SIGN_KERNEL}" = "1" ] || \
        bbfatal "TACTIQ_FIT_SIGN_KERNEL=0 with a verification key in the control FDT: the kernel FIT would be unsigned and the board would not boot"
    [ "${FIT_KERNEL_SIGN_KEYNAME}" = "${TACTIQ_FIT_KEY_NAME}" ] || \
        bbfatal "key name mismatch: control FDT gets '${TACTIQ_FIT_KEY_NAME}', kernel FIT is signed with '${FIT_KERNEL_SIGN_KEYNAME}'"
    [ -f "${TACTIQ_FIT_KEY_DIR}/${TACTIQ_FIT_KEY_NAME}.crt" ] || \
        bbfatal "certificate not found: ${TACTIQ_FIT_KEY_DIR}/${TACTIQ_FIT_KEY_NAME}.crt"
    [ -x "${B}/tools/fdt_add_pubkey" ] || bbfatal "tools/fdt_add_pubkey not built"
    [ -f "${TACTIQ_FIT_CONTROL_DTB}" ] || bbfatal "control FDT not found: ${TACTIQ_FIT_CONTROL_DTB}"

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

    for f in dts/dt.dtb u-boot.dtb u-boot.bin; do
        grep -qa "key-${TACTIQ_FIT_KEY_NAME}" "${B}/$f" || \
            bbfatal "key did not reach $f after rebuild"
    done

    # boot_ab loads from "mmc 0:2" and "mmc 0:4", and env-mmc.cfg keeps the
    # environment on mmc 0: mmc0 must be the SD controller (patch 0002).
    sd="$(fdtget -t s ${B}/u-boot.dtb /aliases mmc0)" || \
        bbfatal "no mmc0 alias in the control FDT: mmc numbering would follow bind order"
    [ "$(fdtget -t s ${B}/u-boot.dtb "$sd" compatible)" = "brcm,bcm2711-emmc2" ] || \
        bbfatal "mmc0 alias in the control FDT is $sd, not the SD controller"
}

do_deploy() {
    install -d ${DEPLOYDIR}
    install -m 0644 ${B}/u-boot.bin ${DEPLOYDIR}/u-boot.bin
    install -m 0644 ${B}/u-boot-initial-env ${DEPLOYDIR}/u-boot-initial-env
}

addtask deploy after do_compile before do_build

do_install[noexec] = "1"
deltask do_install
deltask do_populate_sysroot

PROVIDES = "virtual/bootloader"

COMPATIBLE_MACHINE = "^tactiq-rpi4$"

# cve-check: this recipe is upstream U-Boot
CVE_PRODUCT = "denx:u-boot"
CVE_VERSION = "2026.10"

# Per-recipe CVE report: the bootloader is not part of the rootfs SBOM
inherit sbom-cve-check-recipe
SBOM_CVE_CHECK_SCAN_SCOPE = "target"
addtask sbom_cve_check_recipe after do_create_recipe_sbom before do_deploy

# Board-independent patches (TPM platform hierarchy lock, SM3 gated per
# build phase), the same ones the Rockchip recipe takes. With no TPM
# configured on this board they change nothing in the binary yet; they keep
# the source tree the same patched v2026.10 on both platforms.
require recipes-bsp/u-boot/tactiq-u-boot-common.inc
