# Development keyring: the RAUC trust root is the same pki/dev/ hierarchy
# used for kernel module signing. Its private keys are public by design
# (see pki/README.md). Production builds override RAUC_KEYRING_FILE.
FILESEXTRAPATHS:prepend := "${THISDIR}/files:${LAYERDIR_tactiq-os}/pki/dev:"
RAUC_KEYRING_FILE = "root-ca.pem"
