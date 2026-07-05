# meta-tactiq-bsp-rockchip — linux-yocto bbappend (BSP layer, RK3588-specific).
# BSP counterpart to the core linux-yocto bbappend. Core owns vendor-agnostic
# concerns (security, version pin, extlinux); this owns SoC-specific defconfig
# knobs. Contract (tactiq-rockchip-rk3588.inc): "BSP layer only owns bootloader
# and SoC-specific defconfig knobs." RK3588 USB host is exactly that, so it
# lives here, never in the agnostic core fragment.
FILESEXTRAPATHS:prepend := "${THISDIR}/${PN}:"
SRC_URI += "file://tactiq-rk3588-usb.cfg"
