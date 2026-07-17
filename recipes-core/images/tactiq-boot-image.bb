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

DEPENDS = "e2fsprogs-native virtual/kernel policycoreutils-native"

SRC_URI = "file://boot-file_contexts"

S = "${UNPACKDIR}"

PACKAGE_ARCH = "${MACHINE_ARCH}"

do_compile[depends] += "virtual/kernel:do_deploy"

# Match wks.in boot_a / boot_b partition size (256 MiB).
# RAUC dd's the ext4 image onto the partition — filesystem size must
# equal partition size. Verity bundle format compresses empty blocks.
TACTIQ_BOOT_IMAGE_SIZE_KB ?= "262144"

# Pseudo intercepts chown/xattr only for listed paths;
# boot-root staging dir lives under ${B}, not ${D}.
PSEUDO_INCLUDE_PATHS:append = ",${B}"

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

    # Staging only — mkfs runs in do_install (fakeroot) for SELinux xattrs.
}

do_install() {
    boot_root="${B}/boot-root"

    # Fix ownership (build host uid leak) and set SELinux labels.
    # do_install runs under fakeroot (pseudo): chown and setfiles
    # xattr writes are intercepted and stored in pseudo DB.
    # mkfs.ext4 -d reads them back via lgetxattr → pseudo → ext4 image.
    chown -R 0:0 "$boot_root"
    setfiles -m -r "$boot_root" "${UNPACKDIR}/boot-file_contexts" "$boot_root"

    # Build ext4 image populated from boot_root directory
    img="${B}/${PN}-${MACHINE}.ext4"
    dd if=/dev/zero of="$img" bs=1024 count=${TACTIQ_BOOT_IMAGE_SIZE_KB}
    mkfs.ext4 -F -d "$boot_root" "$img"
}

do_deploy() {
    install -m 0644 "${B}/${PN}-${MACHINE}.ext4" "${DEPLOYDIR}/"
}

addtask deploy after do_install
