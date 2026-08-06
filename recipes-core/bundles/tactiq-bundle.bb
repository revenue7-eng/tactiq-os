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
RAUC_BUNDLE_FORMAT = "verity"
RAUC_BUNDLE_VERSION ?= "${DISTRO_VERSION}"

RAUC_KEY_FILE  ?= "${LAYERDIR_tactiq-os}/pki/dev/signer.key.pem"
RAUC_CERT_FILE ?= "${LAYERDIR_tactiq-os}/pki/dev/signer.pem"
BUNDLE_ARGS += "--intermediate=${LAYERDIR_tactiq-os}/pki/dev/signing-ca.pem"

# --- Slot: rootfs (ext4 image of tactiq-image, production) ---
RAUC_BUNDLE_SLOTS = "rootfs boot"
RAUC_SLOT_rootfs = "tactiq-image"
RAUC_SLOT_rootfs[fstype] = "ext4"

# --- Slot: boot (ext4 image of kernel + dtb + extlinux.conf) ---
RAUC_SLOT_boot = "tactiq-boot-image"
RAUC_SLOT_boot[type] = "boot"
RAUC_SLOT_boot[file] = "tactiq-boot-image.ext4"
