FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

TACTIQ_KEYRING ??= "prod"

RAUC_KEYRING_FILE = "keyring-${TACTIQ_KEYRING}.pem"

SRC_URI:append = " file://system.conf"

python () {
    if d.getVar('TACTIQ_KEYRING') == 'dev':
        bb.warn("TactiQ: DEVELOPMENT keyring - accepts CI-signed bundles. Not for deployment.")
}

# rauc-conf.bb installs the keyring under its source filename, but
# system.conf refers to a fixed path. Normalise the name so that dev and
# prod images ship an identical system.conf and differ only in the
# certificate itself.
do_install:append() {
    mv ${D}${sysconfdir}/rauc/${RAUC_KEYRING_FILE} \
       ${D}${sysconfdir}/rauc/keyring.pem
}
