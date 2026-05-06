FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

SRC_URI:append = " file://system.conf"

# Default to the in-tree development certificate so that a clean check-out
# builds. Production releases MUST override this from CI secrets:
#
#   RAUC_KEYRING_FILE = "${TACTIQ_PROD_KEYRING}"
#
# where TACTIQ_PROD_KEYRING is set in the CI environment (a path to a
# file fetched from a secret store at build time, never committed to
# the source tree). The CI release workflow asserts that a tagged build
# does not resolve RAUC_KEYRING_FILE to the development cert.
RAUC_KEYRING_FILE ?= "${THISDIR}/files/development-1.cert.pem"
