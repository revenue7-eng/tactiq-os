# tactiq-arm64-uboot-base.inc
#
# Vendor-agnostic base for TactiQ ARM64 machines that boot via U-Boot.
# Lives in tactiq-os core layer (meta-tactiq collection), not in any vendor BSP layer — so future
# vendor BSPs (MediaTek, Tegra, ...) require this file directly from
# core without cross-vendor coupling.
#
# What this file owns:
#   - ARM64 toolchain settings
#   - A/B layout variables (TACTIQ_AB_ENABLED, default 0 in rc4)
#   - Boot method extension point (TACTIQ_BOOT_METHOD, default extlinux)
#   - IMAGE_FSTYPES and wks selection
#   - Vendor-agnostic part of IMAGE_BOOT_FILES (kernel + dtb)
#
# What vendor BSP machine configs append:
#   - SoC family (e.g. SOC_FAMILY = "rk3588")
#   - Vendor loader blobs in IMAGE_BOOT_FILES (idbloader.img, u-boot.itb,
#     mt-bootimg, tegra cboot blob, ...)
#   - UBOOT_MACHINE
#   - KERNEL_DEVICETREE for the specific board
#   - PREFERRED_PROVIDER_virtual/bootloader if non-default

# ---- ARM64 baseline ----

# ---- Kernel ----
KERNEL_IMAGETYPE ?= "Image"
# rc5 Stage 1: FIT disabled for extlinux identity-test. Re-add "kernel-fit-image" in rc5/rc6 with fit-signed.
KERNEL_CLASSES   ?= ""
PREFERRED_PROVIDER_virtual/kernel ?= "linux-yocto"

# ---- Extension points ----
# rc4: extlinux only. rc5/rc6 will add "fit-signed".
TACTIQ_BOOT_METHOD ?= "extlinux"

# rc4: boot always from slot A. RAUC bootcount integration is a separate phase.
TACTIQ_AB_ENABLED ?= "0"

# ---- Image format ----
IMAGE_FSTYPES ?= "wic wic.bmap wic.gz ext4 tar.gz"

# ---- IMAGE_BOOT_FILES: vendor-agnostic skeleton ----
#
# NOTE: boot_a partition is NO LONGER populated by WIC via bootimg-partition.
# Boot partition content (kernel Image, DTBs, extlinux.conf) is built by
# tactiq-boot-image.bb with SELinux labels (setfiles + mkfs.ext4 -d) and
# written to boot_a via rawcopy in the wks template. Both WIC initial flash
# and RAUC A/B updates use the same labeled ext4 image — single source of truth.
#
# IMAGE_BOOT_FILES is retained for kernel deploy staging (virtual/kernel
# do_deploy places files listed here into DEPLOY_DIR_IMAGE, where
# tactiq-boot-image.bb picks them up). It does NOT control boot_a content
# directly.
#
# Vendor BSP loader blobs (idbloader.img, u-boot.itb on Rockchip; bl2/fip on
# MediaTek; cboot on Tegra) are NOT in boot_a — they are written to
# raw sector offsets BEFORE the GPT primary by wic --no-table partition
# entries in the BSP-specific .wks template.
IMAGE_BOOT_FILES ?= "${KERNEL_IMAGETYPE} *.dtb boot/extlinux/extlinux.conf"

# ---- Serial ----
SERIAL_CONSOLES ?= "1500000;ttyS2"

# ---- Required by all TactiQ ARM64 boards ----
MACHINE_FEATURES ?= "alsa usbhost ext2 ext3 ext4 vfat"

# ---- Image size guardrails ----
# rc4 wic produced 9.88 GB. Keep ceiling explicit so accidental bloat fails fast.
IMAGE_OVERHEAD_FACTOR ?= "1.0"
IMAGE_ROOTFS_EXTRA_SPACE ?= "524288"

# ---- wic dependency on vendor bootloader ----
# Any ARM64 board booting via U-Boot needs the bootloader artefacts
# (idbloader.img, u-boot.itb, fip, cboot, ...) staged in DEPLOY_DIR_IMAGE
# before wic runs rawcopy. Without this, wic silently consumes whatever
# stale artefacts happen to be in deploy from a previous build —
# bitbake reports SUCCESS while the resulting wic is unbootable.
# This append is vendor-agnostic: every BSP sets PREFERRED_PROVIDER_virtual/bootloader.
WKS_FILE_DEPENDS:append = " virtual/bootloader tactiq-boot-image"

# wrynose: oe-core image_types_wic.bbclass now defaults
# WKS_FILE_DEPENDS_BOOTLOADERS:aarch64 = "grub-efi systemd-boot".
# TactiQ arm64 machines boot via U-Boot + extlinux; EFI bootloaders are
# unused here (and grub-native FTBFS on the build host). Drop them.
WKS_FILE_DEPENDS:remove = "grub-efi systemd-boot"
