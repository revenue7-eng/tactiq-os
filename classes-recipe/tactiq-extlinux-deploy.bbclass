# SPDX-License-Identifier: MIT
#
# License migration note: TactiQ OS currently licenses new code under MIT
# for partnership compatibility. The long-term target license is
# GPL-3.0-or-later. When the project-wide migration occurs, this header
# must be updated together with all other TactiQ-authored sources.

# tactiq-extlinux-deploy.bbclass
#
# Vendor-agnostic delivery mechanism for extlinux.conf in TactiQ OS.
#
# Wraps the standard OE uboot-extlinux-config.bbclass which generates
# ${B}/extlinux.conf but does not install or deploy it. This class adds:
#   - install to ${D}/boot/extlinux/extlinux.conf (rootfs)
#   - deploy to ${DEPLOYDIR}/extlinux-${MACHINE}/extlinux.conf (images dir)
#   - FILES entry for kernel-base package
#
# This class is one of several boot configuration delivery mechanisms in
# TactiQ OS. Different platform families require different mechanisms
# (e.g. GRUB or systemd-boot for x86, vendor-specific bootchains for some
# mobile SoCs); each is implemented as a separate tactiq-*-deploy class.
#
# Currently consumed by: meta-tactiq-bsp-rockchip.
#
# Consumer contract:
#   - Inheriting this class enables extlinux generation; do not override
#     UBOOT_EXTLINUX = "1" unless intentionally disabling it.
#   - Must set UBOOT_EXTLINUX_ROOT (no default; OE class fatals without it).
#   - May override UBOOT_EXTLINUX_LABELS, _KERNEL_IMAGE, _KERNEL_ARGS,
#     _CONSOLE, _FDT, _FDTDIR, _DEFAULT_LABEL, _TIMEOUT, _MENU_TITLE.
#   - BSP layers should override _CONSOLE per their UART conventions and
#     _FDT per their device tree naming.
#
# Out of scope (this class does NOT handle):
#   - Kernel image packaging — kernel.bbclass owns this.
#   - Device tree (.dtb) installation — kernel-devicetree package owns this.
#   - Bootloader binary deployment — u-boot or equivalent recipes own this.
#   - Boot partition layout — wic / IMAGE_BOOT_FILES own this.
#
# Maintainer note: this class exists because uboot-extlinux-config.bbclass
# in oe-core is a generator-only class by design — delivery is consumer
# responsibility. If oe-core ever adds install/deploy stages upstream,
# this class becomes redundant and should be removed in a single commit.

inherit uboot-extlinux-config

# Master flag: enable extlinux.conf generation by the parent class.
# Without this set to "1", do_create_extlinux_config silently returns
# (the parent class does not default it, so every consumer must opt in).
UBOOT_EXTLINUX = "1"

# ---------------------------------------------------------------------------
# Delivery: install to rootfs and deploy to images directory.
#
# The parent class registers do_create_extlinux_config to run before
# do_install and do_deploy via:
#   addtask create_extlinux_config before do_install do_deploy after do_compile
# This guarantees ${B}/extlinux.conf exists when the appends below run.
# ---------------------------------------------------------------------------

do_install:append() {
    install -d ${D}/boot/extlinux
    install -m 0644 ${B}/extlinux.conf ${D}/boot/extlinux/extlinux.conf
}

do_deploy:append() {
    install -d ${DEPLOYDIR}/extlinux-${MACHINE}
    install -m 0644 ${B}/extlinux.conf ${DEPLOYDIR}/extlinux-${MACHINE}/extlinux.conf
}

# extlinux.conf belongs to the same package as /boot/Image and the
# devicetree blobs (kernel-base), so distroboot finds them together.
FILES:${KERNEL_PACKAGE_NAME}-base += "/boot/extlinux/extlinux.conf"
