# TactiQ OS — linux-yocto bbappend (core layer, vendor-agnostic).
#
# Owns three concerns, kept together because they all target linux-yocto
# regardless of which BSP is active:
#   1. Security kernel fragment delivery (tactiq-security.cfg)
#   2. Supply-chain version pinning (PREFERRED_VERSION)
#   3. extlinux configuration via tactiq-extlinux-deploy.bbclass
#
# Per-vendor adjustments (serial console etc.) are made by overriding
# individual UBOOT_EXTLINUX_* variables in BSP layer includes
# (rk3588.inc / mtkXXXX.inc / tegraXXX.inc).

# ===========================================================================
# 1. Security kernel fragment
# ===========================================================================
FILESEXTRAPATHS:prepend := "${THISDIR}/${PN}:"
SRC_URI += "file://tactiq-security.cfg"
SRC_URI += "file://tactiq-netfilter-legacy.cfg"

# ===========================================================================
# 2. Supply-chain pinning (SLSA L2 posture)
# ===========================================================================
# Pin linux-yocto to an exact LTS point release series instead of the "6.6%"
# rolling wildcard so two independent builds resolve to the same kernel tree.
# Review this pin together with a CVE scan before bumping.
PREFERRED_VERSION_linux-yocto = "6.18%"

# TODO(slsa-l2): Add explicit SRCREV_machine / SRCREV_meta pins once the first
# reproducible image is archived with hashes captured from the reference
# scarthgap build. Tracking: internal issue "supply-chain pinning".

# ===========================================================================
# 3. extlinux configuration (tactiq-extlinux-deploy.bbclass)
# ===========================================================================
# The tactiq-extlinux-deploy class (in core layer classes-recipe/) wraps
# oe-core's uboot-extlinux-config.bbclass and adds the install + deploy
# stages that the upstream class deliberately leaves to consumers. It also
# sets the master flag UBOOT_EXTLINUX = "1" so we do not need to repeat it
# here. See classes-recipe/tactiq-extlinux-deploy.bbclass for the contract.

inherit tactiq-extlinux-deploy


# ---- Label / menu identity ----
# Generic label "tactiq" — board-agnostic. RAUC will switch between
# "tactiq" (slot A active) and "tactiq-fallback" (slot B active) by
# regenerating extlinux.conf during slot transitions.
UBOOT_EXTLINUX_LABELS = "tactiq"
UBOOT_EXTLINUX_DEFAULT_LABEL = "tactiq"

# ---- Kernel + DTB paths (relative to boot_a partition root) ----
# Image and DTB live in the root of boot_a. U-Boot bootstd finds extlinux.conf
# at boot_a:/boot/extlinux/extlinux.conf (GPT bootable flag on boot_a only;
# rootfs_a and other partitions are skipped as non-bootable by bootstd).
UBOOT_EXTLINUX_KERNEL_IMAGE = "/${KERNEL_IMAGETYPE}"

# Pick the first DTB from KERNEL_DEVICETREE; basename only, no /boot/ prefix.
# Single-DTB convention is enforced by board configs (rock5a → rk3588s-rock-5a.dtb).
UBOOT_EXTLINUX_FDT = "${@'/' + os.path.basename((d.getVar('KERNEL_DEVICETREE') or '').strip().split()[0]) if (d.getVar('KERNEL_DEVICETREE') or '').strip() else ''}"

# ---- Kernel command line (rc4: slot A only, rc5+ adds RAUC bootcount) ----
UBOOT_EXTLINUX_ROOT ?= "root=PARTLABEL=__RAUC_PART__"
UBOOT_EXTLINUX_KERNEL_ARGS ?= "rootwait rw rootfstype=ext4 earlycon kernel.panic=5"

# Default console: framebuffer only. BSP layers override with serial.
# rk3588.inc:   UBOOT_EXTLINUX_CONSOLE = "console=tty1 console=ttyS2,1500000n8"
UBOOT_EXTLINUX_CONSOLE ?= "console=tty1"

# ===========================================================================
# 4. NPU enablement (NPU-build ONLY — scoped to the "npu" override token)
# ===========================================================================
# These appends fire only for MACHINE=tactiq-rock5a-npu, which injects the
# "npu" override. The hardened release machine (tactiq-rock5a) does not
# carry the token, so neither the rocket kernel fragment nor the NPU device
# tree overlay can enter a release image. Build the NPU machine in a
# SEPARATE build dir; never in the qualified release tmp.
#
# Delivery follows the proven security-fragment path (SRC_URI file://):
#   - tactiq-npu.cfg : DRM_ACCEL + DRM_ACCEL_ROCKET=m + ROCKCHIP_IOMMU=y
#   - 0001-...npu.patch : adds rk3588s-rock-5a-npu.dtso + Makefile *-dtbs rule
SRC_URI:append:npu = " file://tactiq-npu.cfg"
SRC_URI:append:npu = " file://0001-arm64-dts-rk3588s-rock-5a-enable-npu.patch"
