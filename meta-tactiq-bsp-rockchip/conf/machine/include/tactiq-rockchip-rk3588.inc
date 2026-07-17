require conf/machine/include/rk3588-bootrom.inc

# tactiq-rockchip-rk3588.inc
#
# Rockchip RK3588 / RK3588S SoC family include.
# Required by all TactiQ machine configs targeting RK3588(S) boards
# (Rock 5A on RK3588S, Rock 5T on RK3588, future RK3588 boards).
#
# Pulls in the vendor-agnostic ARM64+U-Boot base from core layer,
# then layers on RK3588-specific settings:
#   - cortex-a76 + cortex-a55 big.LITTLE tune
#   - Rockchip loader blobs in IMAGE_BOOT_FILES (idbloader.img + u-boot.itb)
#   - u-boot-rockchip as bootloader provider
#   - Rockchip-specific wic template
#
# Board-specific machine configs (tactiq-rock5a.conf, tactiq-rock5t.conf)
# require this file, then set KERNEL_DEVICETREE, UBOOT_MACHINE, and
# MACHINE_FEATURES.

# ---- Vendor-agnostic base (lives in tactiq-os core, meta-tactiq collection) ----
require conf/machine/include/tactiq-arm64-uboot-base.inc

# ---- SoC family ----
SOC_FAMILY = "rk3588"
MACHINEOVERRIDES =. "rk3588:"

# ---- ARM64 tune for RK3588 (big.LITTLE Cortex-A76 + Cortex-A55) ----
require conf/machine/include/arm/armv8-2a/tune-cortexa76-cortexa55.inc

# ---- Bootloader: Rockchip U-Boot ----
PREFERRED_PROVIDER_virtual/bootloader = "u-boot-rockchip"

# ---- Kernel ----
# PREFERRED_PROVIDER + PREFERRED_VERSION live in core layer's linux-yocto
# bbappend (recipes-kernel/linux/linux-yocto_%.bbappend) — kernel version
# is a distro-level decision, not a vendor BSP one. BSP layer only owns
# bootloader and SoC-specific defconfig knobs.
PREFERRED_PROVIDER_virtual/kernel = "linux-yocto"
KBUILD_DEFCONFIG = "defconfig"
KCONFIG_MODE = "alldefconfig"

# ---- Rockchip-specific wic template ----
WKS_FILE = "tactiq-ab-rockchip.wks.in"

# ---- IMAGE_BOOT_FILES on Rockchip ----
#
# No override needed. Base provides "${KERNEL_IMAGETYPE} *.dtb" — that is the
# full content of boot_a partition.
#
# Rockchip loader blobs are written directly to raw sectors via wic rawcopy
# in tactiq-ab-rockchip.wks.in:
#     idbloader.img @ sector 64    (TPL + SPL)
#     u-boot.itb    @ sector 16384 (ATF + OP-TEE + U-Boot proper)
# These live BEFORE the GPT primary header — required by RK3588 BootROM contract.

# ---- extlinux: RK3588 serial console override ----
#
# Core layer's linux-yocto bbappend defaults UBOOT_EXTLINUX_CONSOLE to "console=tty1".
# RK3588 boards expose UART on ttyS2 @ 1500000 baud — override here so all
# boards in the RK3588 family get the same serial console in the kernel cmdline.
UBOOT_EXTLINUX_CONSOLE = "console=tty1 console=ttyS2,1500000n8"

# ---- RAUC: identify booted slot to userspace ----
# U-Boot boot_ab sets rauc_slot/rauc_part env vars per slot before sysboot.
# extlinux.conf uses ${rauc_slot} placeholder, resolved at boot time.
UBOOT_EXTLINUX_KERNEL_ARGS:append = " rauc.slot=__RAUC_SLOT__"
