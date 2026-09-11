SUMMARY = "Per-slot device trees carrying verity bootargs in /chosen"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

# kernel-fit-image.bbclass keys off this: when a virtual/dtb provider exists it
# sets EXTERNAL_KERNEL_DEVICETREE to ${RECIPE_SYSROOT}/boot/devicetree itself
# and adds the task dependency. Nothing here sets that variable by hand.
PROVIDES = "virtual/dtb"
DEPENDS = "dtc-native"

PACKAGE_ARCH = "${MACHINE_ARCH}"
S = "${UNPACKDIR}"
INHIBIT_DEFAULT_DEPS = "1"
do_configure[noexec] = "1"

# /boot is not staged into recipe sysroots by default.
SYSROOT_DIRS += "/boot"

# Which image profile produces the verity parameters. Production by default;
# override in local.conf for bring-up builds.
TACTIQ_VERITY_IMAGE ?= "tactiq-image"

# Block devices as seen by the kernel on this board. Machine-specific.
TACTIQ_SLOT_A_DEV ?= "/dev/mmcblk0p2"
TACTIQ_SLOT_B_DEV ?= "/dev/mmcblk0p4"

TACTIQ_COMMON_BOOTARGS ?= "ro rootwait rootfstype=ext4 earlycon panic=5 console=tty1 console=ttyS2,1500000n8"

# do_image_verity, not do_image_complete: the latter includes do_image_wic,
# which depends on the boot image, which will depend on the FIT, which depends
# on this recipe. That would be a cycle.
do_compile[depends] += "virtual/kernel:do_deploy ${TACTIQ_VERITY_IMAGE}:do_image_verity"

do_compile() {
    src_name="$(basename ${@d.getVar('KERNEL_DEVICETREE').split()[0]})"
    src="${DEPLOY_DIR_IMAGE}/${src_name}"
    [ -f "$src" ] || bbfatal "device tree not in deploy: $src"

    params="$(ls ${DEPLOY_DIR_IMAGE}/${TACTIQ_VERITY_IMAGE}-${MACHINE}*.ext4.verity-params 2>/dev/null | head -1)"
    [ -n "$params" ] || bbfatal "no .ext4.verity-params for ${TACTIQ_VERITY_IMAGE} in ${DEPLOY_DIR_IMAGE}"
    # bitbake expands VERITY_SALT itself (it exists in the datastore via
    # conf/distro/tactiq.conf) before the shell ever sees the line, so the
    # value would come from the distro config rather than from the artefact.
    # Rename on the way in: P_* names cannot collide with datastore ones.
    sed "s/^VERITY_/P_VERITY_/" "$params" > "${B}/verity.env"
    . "${B}/verity.env"

    for v in P_VERITY_DATA_SECTORS P_VERITY_DATA_BLOCKS P_VERITY_DATA_BLOCK_SIZE \
             P_VERITY_HASH_BLOCK_SIZE P_VERITY_HASH_ALGORITHM P_VERITY_ROOT_HASH P_VERITY_SALT; do
        eval "val=\$$v"
        [ -n "$val" ] || bbfatal "$v empty in $params"
    done

    # No superblock in the artefact, so the hash tree starts at the block right
    # after the data blocks: hash_start equals VERITY_DATA_BLOCKS.
    emit_dtb() {
        out="$1"; dev="$2"; slot="$3"
        install -m 0644 "$src" "${B}/$out"
        args="dm-mod.create=\"rootfs,,,ro,0 $P_VERITY_DATA_SECTORS verity 1 $dev $dev"
        args="$args $P_VERITY_DATA_BLOCK_SIZE $P_VERITY_HASH_BLOCK_SIZE"
        args="$args $P_VERITY_DATA_BLOCKS $P_VERITY_DATA_BLOCKS $P_VERITY_HASH_ALGORITHM"
        args="$args $P_VERITY_ROOT_HASH $P_VERITY_SALT 1 ignore_zero_blocks\""
        args="$args root=/dev/dm-0 ${TACTIQ_COMMON_BOOTARGS} rauc.slot=$slot"
        [ -n "${TACTIQ_EXTRA_BOOTARGS}" ] && args="$args ${TACTIQ_EXTRA_BOOTARGS}"
        fdtput -t s "${B}/$out" /chosen bootargs "$args"
        got="$(fdtget -t s "${B}/$out" /chosen bootargs)"
        [ "$got" = "$args" ] || bbfatal "bootargs readback mismatch in $out"
    }

    # Slot A keeps the original file name on purpose: kernel-fit-image skips a
    # KERNEL_DEVICETREE entry when a same-named non-empty file exists in the
    # external directory. That displacement is what keeps a configuration
    # without verity out of the FIT.
    emit_dtb "$src_name" "${TACTIQ_SLOT_A_DEV}" A
    emit_dtb "${src_name%.dtb}-b.dtb" "${TACTIQ_SLOT_B_DEV}" B
}

do_install() {
    install -d ${D}/boot/devicetree
    install -m 0644 ${B}/*.dtb ${D}/boot/devicetree/
}

FILES:${PN} = "/boot/devicetree"
