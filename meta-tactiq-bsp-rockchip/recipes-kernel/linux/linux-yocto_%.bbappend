# meta-tactiq-bsp-rockchip — linux-yocto bbappend (BSP layer, RK3588-specific).
# BSP counterpart to the core linux-yocto bbappend. Core owns vendor-agnostic
# concerns (security, version pin, extlinux); this owns SoC-specific defconfig
# knobs. Contract (tactiq-rockchip-rk3588.inc): "BSP layer only owns bootloader
# and SoC-specific defconfig knobs." RK3588 USB host is exactly that, so it
# lives here, never in the agnostic core fragment.
FILESEXTRAPATHS:prepend := "${THISDIR}/${PN}:"
SRC_URI += "file://tactiq-rk3588-usb.cfg"

# VIVID virtual V4L2 driver — attached ONLY in spike builds (TACTIQ_SPIKE=1 in
# local.conf). Keeps the emulator out of the product kernel (§ product-vs-measurement).
SRC_URI += "${@bb.utils.contains('TACTIQ_SPIKE', '1', 'file://tactiq-vivid-spike.cfg', '', d)}"
