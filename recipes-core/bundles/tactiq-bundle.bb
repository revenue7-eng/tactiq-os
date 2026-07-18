# TactiQ OS update bundle for Rock 5A (A/B OTA via RAUC)
#
# Build:  bitbake tactiq-bundle
# Output: tmp/deploy/images/tactiq-rock5a/tactiq-bundle-tactiq-rock5a.raucb
#
# Signing keys configured in local.conf:
#   RAUC_KEY_FILE  = "/mnt/d/tactiq-os/recipes-core/rauc/files/dev-signing.key.pem"
#   RAUC_CERT_FILE = "/mnt/d/tactiq-os/recipes-core/rauc/files/dev-signing.cert.pem"

inherit bundle
S = "${UNPACKDIR}"

RAUC_BUNDLE_COMPATIBLE = "TactiQ OS Rock5A"
RAUC_BUNDLE_FORMAT = "verity"
RAUC_BUNDLE_VERSION ?= "${DISTRO_VERSION}"

# --- Slot: rootfs (ext4 image of tactiq-image, production) ---
RAUC_BUNDLE_SLOTS = "rootfs boot"
RAUC_SLOT_rootfs = "tactiq-image"
RAUC_SLOT_rootfs[fstype] = "ext4"

# --- Slot: boot (ext4 image of kernel + dtb + extlinux.conf) ---
RAUC_SLOT_boot = "tactiq-boot-image"
RAUC_SLOT_boot[type] = "boot"
RAUC_SLOT_boot[file] = "tactiq-boot-image.ext4"
