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
KERNEL_CLASSES   ?= "kernel-fitimage"
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
# boot_a partition contents: kernel Image + DTB(s).
# extlinux.conf is NOT in boot_a — it is deployed to rootfs /boot/extlinux/
# by uboot-extlinux-config.bbclass. U-Boot distroboot scans the rootfs
# partition (PARTLABEL=rootfs_a) and finds extlinux.conf there. This is
# vendor-agnostic: same mechanism on Rockchip, MediaTek, Tegra, x86.
#
# Vendor BSP loader blobs (idbloader.img, u-boot.itb on Rockchip; bl2/fip on
# MediaTek; cboot on Tegra) are NOT in boot_a either — they are written to
# raw sector offsets BEFORE the GPT primary by wic --no-table partition
# entries in the BSP-specific .wks template.
IMAGE_BOOT_FILES ?= "${KERNEL_IMAGETYPE} *.dtb"

# ---- Serial ----
SERIAL_CONSOLES ?= "1500000;ttyS2"

# ---- Required by all TactiQ ARM64 boards ----
MACHINE_FEATURES ?= "alsa usbhost ext2 ext3 ext4 vfat"

# ---- Image size guardrails ----
# rc4 wic produced 9.88 GB. Keep ceiling explicit so accidental bloat fails fast.
IMAGE_OVERHEAD_FACTOR ?= "1.0"
IMAGE_ROOTFS_EXTRA_SPACE ?= "524288"
