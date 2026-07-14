FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

# Which trust anchor this image ships with.
#
#   prod (default) — /etc/rauc/keyring.pem is the production root CA.
#                    Only bundles resigned offline with the production
#                    key install on this image.
#
#   dev            — the development root CA (pki/dev/root-ca.pem).
#                    Installs CI-signed bundles. Never ship this.
#
# Default is prod, and a missing production root is a build failure,
# not a silent fallback to the dev certificate.
TACTIQ_KEYRING ??= "prod"

SRC_URI:append = " file://system.conf"

RAUC_KEYRING_FILE = "keyring.pem"

SRC_URI:append = " file://keyring-${TACTIQ_KEYRING}.pem;subdir=keyring"

do_configure:prepend() {
    if [ "${TACTIQ_KEYRING}" = "dev" ]; then
        bbwarn "TactiQ: DEVELOPMENT keyring — this image accepts CI-signed bundles. Not for deployment."
    fi
    install -m 0644 ${UNPACKDIR}/keyring/keyring-${TACTIQ_KEYRING}.pem \
                    ${UNPACKDIR}/${RAUC_KEYRING_FILE}
}
