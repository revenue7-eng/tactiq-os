FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

TACTIQ_KEYRING ??= "prod"

RAUC_KEYRING_FILE = "keyring-${TACTIQ_KEYRING}.pem"

SRC_URI:append = " file://system.conf"

python () {
    if d.getVar('TACTIQ_KEYRING') == 'dev':
        bb.warn("TactiQ: DEVELOPMENT keyring - accepts CI-signed bundles. Not for deployment.")
}
