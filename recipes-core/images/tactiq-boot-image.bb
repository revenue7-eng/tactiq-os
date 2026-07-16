# TactiQ OS boot partition image (kernel + dtb + extlinux)
#
# Standalone ext4 image of the boot partition for RAUC A/B slot updates.
# Contains kernel Image, device tree blob(s), and extlinux.conf with
# U-Boot variable placeholders (${rauc_part}, ${rauc_slot}) resolved
# at boot time by U-Boot sysboot.
#
# Build: MACHINE=tactiq-rock5a bitbake tactiq-boot-image
# Output: tmp/deploy/images/tactiq-rock5a/tactiq-boot-image-tactiq-rock5a.ext4
SUMMARY = "TactiQ OS boot partition image (kernel + dtb + extlinux)"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

inherit deploy

DEPENDS = "e2fsprogs-native virtual/kernel"

PACKAGE_ARCH = "${MACHINE_ARCH}"

do_compile[depends] += "virtual/kernel:do_deploy"

# Match wks.in boot_a / boot_b partition size (256 MiB).
# RAUC dd's the ext4 image onto the partition — filesystem size must
# equal partition size. Verity bundle format compresses empty blocks.
TACTIQ_BOOT_IMAGE_SIZE_KB ?= "262144"

do_compile() {
    boot_root="${B}/boot-root"
    rm -rf "$boot_root"
    install -d "$boot_root/boot/extlinux"

    # Kernel
    install -m 0644 "${DEPLOY_DIR_IMAGE}/${KERNEL_IMAGETYPE}" "$boot_root/"

    # Device tree blob(s)
    for dtb_path in ${KERNEL_DEVICETREE}; do
        install -m 0644 "${DEPLOY_DIR_IMAGE}/$(basename $dtb_path)" "$boot_root/"
    done

    # extlinux.conf — contains ${rauc_part} / ${rauc_slot} placeholders
    install -m 0644 "${DEPLOY_DIR_IMAGE}/boot/extlinux/extlinux.conf" \
        "$boot_root/boot/extlinux/"

    # Build ext4 image populated from boot_root directory
    img="${B}/${PN}-${MACHINE}.ext4"
    dd if=/dev/zero of="$img" bs=1024 count=${TACTIQ_BOOT_IMAGE_SIZE_KB}
    mkfs.ext4 -F -d "$boot_root" "$img"
}

do_deploy() {
    install -m 0644 "${B}/${PN}-${MACHINE}.ext4" "${DEPLOYDIR}/"
}

addtask deploy after do_compile
