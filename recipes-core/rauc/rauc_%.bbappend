FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

SRC_URI:append = " file://system.conf"

RAUC_KEYRING_FILE = "${THISDIR}/files/development-1.cert.pem"
