SUMMARY = "U-Boot bootloader for Rockchip RK35xx (Kwiboo fork)"
DESCRIPTION = "Builds Kwiboo's U-Boot fork (rk3xxx-2024.07 branch) for Rockchip \
RK35xx targets. This fork contains RK3588 patches not yet merged into mainline. \
Same commit (8cdf606e) used by meta-rockchip bbappend for RK3588 boards. \
Mainline did not boot RK3588 when this recipe was written; v2026.10 does. \
Source: https://github.com/Kwiboo/u-boot-rockchip/tree/rk3xxx-2024.07"

LICENSE = "GPL-2.0-or-later"
LIC_FILES_CHKSUM = "file://Licenses/README;md5=2ca5f2c35c8cc335f0a19756634782f1"

# Fallback only, from rc14 on: u-boot-rockchip_2026.10.bb is the default.
# Kept for one release so that a release build can go back to it with
# PREFERRED_VERSION_u-boot-rockchip = "2024.07-kwiboo"; to be removed after rc14.
DEFAULT_PREFERENCE = "-1"

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
SRC_URI += "file://0005-configs-rock5a-declare-writeable-env-variables.patch"
SRC_URI += "file://0006-arm64-dts-rk3588s-rock-5a-reserve-tpm-event-log.patch"
SRC_URI += "file://0007-rockchip-rk3588s-rock-5a-measure-SPL-loaded-images.patch"
SRC_URI += "file://0008-rockchip-add-vm-uuid-derived-from-the-SoC-cpuid.patch"
SRC_URI += "file://0009-boot-fit-build-signed-node-list-CVE-2026-46728.patch"
SRC_URI += "file://0010-fdt-check-return-value-of-fdt_get_name.patch"
SRC_URI += "file://0011-image-fit-sig-validate-hashed-strings-size.patch"
SRC_URI += "file://0012-fdt_region-check-fdt_get_property_by_offset.patch"
SRC_URI += "file://0013-image-fit-limit-fdt_check_no_at-depth.patch"
SRC_URI += "file://0014-image-fit-validate-external-data-bounds.patch"
SRC_URI += "file://0015-ext4-fix-integer-overflow-in-ext4fs_read_symlink-CVE-2024-57256.patch"
SRC_URI += "file://0016-boot-lock-the-TPM-platform-hierarchy-before-the-OS.patch"
SRC_URI += "file://0017-dlmalloc-fix-integer-overflow-in-sbrk-CVE-2024-57258.patch"
SRC_URI += "file://0018-dlmalloc-fix-integer-overflow-in-request2size-CVE-2024-57258.patch"
SRC_URI += "file://net-off.cfg"
SRC_URI += "file://env-mmc.cfg"
SRC_URI += "file://boot-ab.cfg"
SRC_URI += "file://env-lockdown.cfg"
SRC_URI += "file://fit-signature.cfg"
SRC_URI += "file://tpm-spi.cfg"
SRC_URI += "file://measured-boot.cfg"
SRC_URI += "file://tpm-lock.cfg"
SRC_URI += "file://spl-measured-boot.cfg"
SRC_URI += "file://machine-id.cfg"
SRC_URI += "file://console-lockdown.cfg"
SRC_URI += "file://tactiq-boot.env"
SRC_URI += "file://tactiq-boot-fit.env"

# Default environment by boot method. "fit" boots the signed FIT with bootm
# and never reads extlinux.conf; "extlinux" keeps sysboot.
TACTIQ_UBOOT_ENV = "${@'tactiq-boot-fit.env' if d.getVar('TACTIQ_BOOT_METHOD') == 'fit' else 'tactiq-boot.env'}"
# FIT configuration names follow kernel-fit-image (conf-<dtb basename>) and
# the per-slot devicetrees of tactiq-slot-dtb.bb (slot B adds "-b").
TACTIQ_FIT_DTB = "${@os.path.basename(d.getVar('KERNEL_DEVICETREE').split()[0])}"
do_configure[vardeps] += "TACTIQ_UBOOT_ENV TACTIQ_FIT_DTB"

# Interactive U-Boot console, for bench builds only. Off unless a build sets
# it to "1" in its own local.conf. A loader carrying a FIT key other than the
# development key is never built with it (checked in do_configure).
TACTIQ_UBOOT_CONSOLE ??= "0"
do_configure[vardeps] += "TACTIQ_UBOOT_CONSOLE TACTIQ_FIT_KEY_NAME"

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
    if [ "${TACTIQ_UBOOT_CONSOLE}" = "1" ] && [ "${TACTIQ_FIT_KEY_NAME}" != "dev-fit" ]; then
        bbfatal "TACTIQ_UBOOT_CONSOLE=1 with FIT key '${TACTIQ_FIT_KEY_NAME}': the console is for development loaders only"
    fi
    lockdown=""
    [ "${TACTIQ_UBOOT_CONSOLE}" = "1" ] || lockdown="${UNPACKDIR}/console-lockdown.cfg"
    ${S}/scripts/kconfig/merge_config.sh -O ${B} -m ${B}/.config ${UNPACKDIR}/env-mmc.cfg ${UNPACKDIR}/boot-ab.cfg ${UNPACKDIR}/env-lockdown.cfg ${UNPACKDIR}/fit-signature.cfg ${UNPACKDIR}/tpm-spi.cfg ${UNPACKDIR}/measured-boot.cfg ${UNPACKDIR}/tpm-lock.cfg ${UNPACKDIR}/spl-measured-boot.cfg ${UNPACKDIR}/machine-id.cfg ${UNPACKDIR}/net-off.cfg ${lockdown}
    dtb="${TACTIQ_FIT_DTB}"
    sed -e "s|@FIT_CONF_A@|conf-${dtb}|g" -e "s|@FIT_CONF_B@|conf-${dtb%.dtb}-b.dtb|g" \
        ${UNPACKDIR}/${TACTIQ_UBOOT_ENV} > ${S}/tactiq-boot.env
    if grep -q "@FIT_CONF_" ${S}/tactiq-boot.env; then
        bbfatal "unresolved FIT configuration placeholder in ${TACTIQ_UBOOT_ENV}"
    fi
    oe_runmake -C ${S} O=${B} olddefconfig
    # olddefconfig drops a symbol with unmet dependencies without a word.
    grep -q '^CONFIG_OF_BOARD_SETUP=y$' ${B}/.config || \
        bbfatal "CONFIG_OF_BOARD_SETUP did not survive olddefconfig: no vm,uuid, machine-id stays random"
    grep -q '^CONFIG_MEASURED_BOOT=y$' ${B}/.config || \
        bbfatal "CONFIG_MEASURED_BOOT did not survive olddefconfig"
    grep -q '^CONFIG_TPM_V2=y$' ${B}/.config || \
        bbfatal "CONFIG_TPM_V2 did not survive olddefconfig"
    grep -q '^CONFIG_MEASURED_BOOT_LOCK_PLATFORM=y$' ${B}/.config || \
        bbfatal "CONFIG_MEASURED_BOOT_LOCK_PLATFORM did not survive olddefconfig: the OS would get the TPM platform hierarchy"
    ! grep -qE '^CONFIG_(NET|FS_SQUASHFS|CMD_SQUASHFS)=y$' ${B}/.config || \
        bbfatal "network or squashfs support is enabled: the CVE_STATUS entries of this recipe would be false"
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

# cve-check: this recipe is upstream U-Boot (kwiboo rk3xxx-2024.07 branch)
CVE_PRODUCT = "denx:u-boot"
CVE_VERSION = "2024.07"

# CVEs in code this loader does not build. do_configure fails if either
# option comes back, so these statuses cannot outlive the configuration
# they describe. CVE-2024-57258 is reached through squashfs but sits in the
# allocator, which this loader does build: it is fixed by 0017 and 0018.
CVE_STATUS_GROUPS += "CVE_STATUS_UBOOT_SQUASHFS CVE_STATUS_UBOOT_NET"
CVE_STATUS_UBOOT_SQUASHFS = "CVE-2024-57254 CVE-2024-57255 CVE-2024-57257 CVE-2024-57259"
CVE_STATUS_UBOOT_SQUASHFS[status] = "not-applicable-config: squashfs support is not built (CONFIG_FS_SQUASHFS and CONFIG_CMD_SQUASHFS are not set)"
CVE_STATUS_UBOOT_NET = "CVE-2024-42040 CVE-2026-29007 CVE-2026-29008 CVE-2026-29009"
CVE_STATUS_UBOOT_NET[status] = "not-applicable-config: the network stack is not built (net-off.cfg; CONFIG_NET is not set)"

# Per-recipe CVE report: the bootloader is not part of the rootfs SBOM
inherit sbom-cve-check-recipe
SBOM_CVE_CHECK_SCAN_SCOPE = "target"
# Run with every loader build, so the release always has a report for the
# loader it ships (the image build pulls this recipe through do_deploy).
addtask sbom_cve_check_recipe after do_create_recipe_sbom before do_deploy
