# TactiQ OS update bundle for Rock 5A (A/B OTA via RAUC)
#
# Build:  bitbake tactiq-bundle
# Output: tmp/deploy/images/tactiq-rock5a/tactiq-bundle-tactiq-rock5a.raucb
#
# Signing keys ship with the tag. The development private keys are public
# by design (see pki/README.md), so a bundle this image accepts can be built
# by anyone, without local configuration. Production builds override these
# from CI secrets and re-sign offline via `rauc resign`.
#
# The signer is issued by an intermediate CA, so the intermediate must be
# embedded in the CMS signature: without it a verifier holding only the root
# reports "unable to get local issuer certificate". rauc takes it via
# --intermediate, passed through BUNDLE_ARGS.

inherit bundle
S = "${UNPACKDIR}"

RAUC_BUNDLE_COMPATIBLE = "TactiQ OS Rock5A"
RAUC_BUNDLE_COMPATIBLE:tactiq-rock5t = "TactiQ OS Rock5T"
RAUC_BUNDLE_FORMAT = "verity"
require recipes-core/tactiq-release/release-derived.inc
RAUC_BUNDLE_VERSION = "${TACTIQ_RAUC_VERSION}"

RAUC_KEY_FILE  ?= "${LAYERDIR_tactiq-os}/pki/dev/signer.key.pem"
RAUC_CERT_FILE ?= "${LAYERDIR_tactiq-os}/pki/dev/signer.pem"
RAUC_INTERMEDIATE_FILE ?= "${LAYERDIR_tactiq-os}/pki/dev/signing-ca.pem"
BUNDLE_ARGS += "--intermediate=${RAUC_INTERMEDIATE_FILE}"

# --- Slot: rootfs (the verity image of TACTIQ_VERITY_IMAGE) ---
# The boot slot carries a FIT whose slot devicetrees hold the dm-verity root
# hash of TACTIQ_VERITY_IMAGE (tactiq-slot-dtb.bb). The rootfs in the bundle
# must be that same image, or the installed slot fails verity on its first
# boot. Taking it from the same variable keeps the two from drifting apart;
# a build that sets RAUC_SLOT_rootfs on its own can no longer pair a rootfs
# with another image's root hash.
RAUC_BUNDLE_SLOTS = "rootfs boot"
RAUC_SLOT_rootfs = "${TACTIQ_VERITY_IMAGE}"
RAUC_SLOT_rootfs[fstype] = "ext4.verity"
RAUC_SLOT_rootfs[rename] = "rootfs.ext4"

# --- Slot: boot (ext4 image of kernel + dtb + extlinux.conf) ---
RAUC_SLOT_boot = "tactiq-boot-image"
RAUC_SLOT_boot[type] = "boot"
RAUC_SLOT_boot[file] = "tactiq-boot-image.ext4"
