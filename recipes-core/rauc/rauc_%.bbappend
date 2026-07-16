# TactiQ OS — RAUC keyring posture
#
# Weak-assign the development CA so that CI can override with a
# production keyring via RAUC_KEYRING_FILE in local.conf or env.
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
RAUC_KEYRING_FILE ?= "${THISDIR}/files/development-1.cert.pem"
