# SPDX-License-Identifier: MIT
#
# License migration note: TactiQ OS currently licenses new code under MIT
# for partnership compatibility. The long-term target license is
# GPL-3.0-or-later. When the project-wide migration occurs, this header
# must be updated together with all other TactiQ-authored sources.

# image_types_bootext4.bbclass
#
# Boot partition image built as an image type of the rootfs recipe rather
# than as a separate recipe.
#
# Why this is a type and not a recipe: the boot partition must eventually
# carry the verity root hash of the rootfs it belongs to. A separate recipe
# cannot read that hash, because WKS_FILE_DEPENDS pulls the boot recipe into
# the image sysroot, so any dependency of the boot recipe on an artefact of
# the image closes a dependency ring. Built as a type of the image recipe,
# the task simply runs after do_image_verity in the same recipe.
#
# Produces ${IMGDEPLOYDIR}/${IMAGE_NAME}.bootext4, an ext4 filesystem sized
# to the boot partition, populated with kernel, device tree blobs and
# extlinux.conf, carrying SELinux labels applied with setfiles.
#
# Consumer contract:
#   - The image recipe inherits this class and adds "bootext4" to
#     IMAGE_FSTYPES.
#   - wic references the artefact as ${IMAGE_LINK_NAME}.bootext4; the
#     symlink is created by image.bbclass from the subimage list.
#   - TACTIQ_BOOT_IMAGE_SIZE_KB must match the boot partition size in the
#     wks file. RAUC dd's this image onto the partition, so the filesystem
#     size must equal the partition size.
#
# Out of scope (this class does NOT handle):
#   - Kernel and dtb generation; the kernel recipe owns those.
#   - extlinux.conf generation; tactiq-extlinux-deploy.bbclass owns that.
#   - Partition layout; the wks file owns that.
#
# Replaces recipes-core/images/tactiq-boot-image.bb, which stays in the tree
# only until the RAUC bundle stops referencing it.

inherit image-artifact-names

do_image_bootext4[depends] += "e2fsprogs-native:do_populate_sysroot"
do_image_bootext4[depends] += "policycoreutils-native:do_populate_sysroot"
do_image_bootext4[depends] += "virtual/kernel:do_deploy"

# Ordering only: the boot image must be built after the verity artefact,
# because a later step puts the verity root hash into the boot payload.
IMAGE_TYPEDEP:bootext4 = "verity"

# Match the boot_a / boot_b partition size in the wks file.
TACTIQ_BOOT_IMAGE_SIZE_KB ?= "262144"

# File contexts for the boot filesystem, read from the layer rather than
# through SRC_URI: this class is inherited by an image recipe whose SRC_URI
# is not ours to extend.
TACTIQ_BOOT_FILE_CONTEXTS ?= "${LAYERDIR_tactiq-os}/recipes-core/images/files/boot-file_contexts"

# Staging directory for the boot filesystem. Pseudo only intercepts chown
# and xattr calls for the paths listed in PSEUDO_INCLUDE_PATHS, and that
# list names specific directories under WORKDIR, not WORKDIR itself, so
# this one has to be added explicitly or chown fails with EINVAL.
TACTIQ_BOOTEXT4_ROOT ?= "${WORKDIR}/bootext4-root"
PSEUDO_INCLUDE_PATHS:append = ",${TACTIQ_BOOTEXT4_ROOT}"

IMAGE_CMD:bootext4 () {
	boot_root="${TACTIQ_BOOTEXT4_ROOT}"
	rm -rf "$boot_root"
	install -d "$boot_root/boot/extlinux"

	install -m 0644 "${DEPLOY_DIR_IMAGE}/${KERNEL_IMAGETYPE}" "$boot_root/"

	for dtb_path in ${KERNEL_DEVICETREE}; do
		install -m 0644 "${DEPLOY_DIR_IMAGE}/$(basename $dtb_path)" "$boot_root/"
	done

	install -m 0644 "${DEPLOY_DIR_IMAGE}/boot/extlinux/extlinux.conf" \
		"$boot_root/boot/extlinux/"

	# do_image tasks run under fakeroot, so chown and the xattrs written by
	# setfiles are intercepted by pseudo and read back by mkfs.ext4 -d.
	chown -R 0:0 "$boot_root"
	setfiles -m -r "$boot_root" "${TACTIQ_BOOT_FILE_CONTEXTS}" "$boot_root"

	img="${IMGDEPLOYDIR}/${IMAGE_NAME}.bootext4"
	dd if=/dev/zero of="$img" bs=1024 count=${TACTIQ_BOOT_IMAGE_SIZE_KB}
	mkfs.ext4 -F -d "$boot_root" "$img"
}
