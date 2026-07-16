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
RAUC_BUNDLE_VERSION ?= "1.0.0"

# --- Slot: rootfs (ext4 image of tactiq-image-dev) ---
RAUC_BUNDLE_SLOTS = "rootfs"
RAUC_SLOT_rootfs = "tactiq-image-dev"
RAUC_SLOT_rootfs[fstype] = "ext4"

# Boot slot (kernel + dtb + extlinux) is NOT in V1 bundle.
# Rationale: boot partition changes only on kernel/dtb upgrade,
# rootfs changes on every software update. Adding boot slot
# requires a dedicated boot-image recipe — deferred to V2.
