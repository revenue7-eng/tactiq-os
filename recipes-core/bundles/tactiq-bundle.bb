SUMMARY = "TactiQ OS update bundle"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

inherit bundle

# bundle.bbclass predates wrynose and sets S = ${WORKDIR}, which wrynose
# rejects. BUNDLE_DIR derives from S, so it must point somewhere valid.
S = "${UNPACKDIR}"

RAUC_BUNDLE_SLOTS = "rootfs"
RAUC_SLOT_rootfs = "tactiq-image-dev"
RAUC_SLOT_rootfs[fstype] = "ext4"

# Must match [system] compatible in system.conf. A mismatch is one of the
# negative tests: a bundle built for another machine must be rejected.
RAUC_BUNDLE_COMPATIBLE = "tactiq-edge"
RAUC_BUNDLE_VERSION = "${DISTRO_VERSION}"
RAUC_BUNDLE_FORMAT = "verity"

TACTIQ_PKI = "${LAYERDIR_tactiq-os}/pki"

# Development signing. The private key is public on purpose (pki/README.md):
# it lets anyone reproduce the negative test in which a production image
# rejects a CI-signed bundle. Release bundles are not signed here - they are
# resigned offline with the production key.
RAUC_CERT_FILE = "${TACTIQ_PKI}/dev/signer.pem"
RAUC_KEY_FILE = "${TACTIQ_PKI}/dev/signer.key.pem"

# The signing CA must travel inside the bundle signature: the device keyring
# holds the root only. bundle.bbclass has no variable for this, so it goes
# through BUNDLE_ARGS.
BUNDLE_ARGS += "--intermediate=${TACTIQ_PKI}/dev/signing-ca.pem"
