# tactiq-keygate: one gate for every signing anchor taken from pki/dev/.
#
# TACTIQ_KEYRING = "dev" (the default) builds with the in-tree development
# PKI, whose private keys are public by design (pki/README.md). Any other
# value declares a production build. Every anchor listed in
# TACTIQ_KEYGATE_VARS must then be set in the configuration (local.conf or
# the CI environment) to material outside pki/dev/.
#
# The check runs once, when the configuration is parsed, so a production
# build stops before any task runs and names each anchor at fault. Anchors
# whose default lives in a recipe (the bundle signer, the module signing
# key) are not visible at this point; left at their recipe default, they are
# reported as not set, which is the intended result.
#
# Anchors:
#   RAUC_KEYRING_FILE_EXTERNAL  RAUC trust root installed in the image
#   RAUC_KEY_FILE, RAUC_CERT_FILE, RAUC_INTERMEDIATE_FILE
#                               bundle signer and its intermediate CA
#   IMA_EVM_PRIVKEY, IMA_EVM_X509, IMA_EVM_ROOT_CA
#                               IMA appraisal signer and its trust chain
#   TACTIQ_FIT_KEY_DIR          FIT verification key in the U-Boot FDT
#   TACTIQ_MODULE_SIG_KEY       kernel module signing key and built-in cert

TACTIQ_KEYGATE_VARS ?= "\
    RAUC_KEYRING_FILE_EXTERNAL \
    RAUC_KEY_FILE RAUC_CERT_FILE RAUC_INTERMEDIATE_FILE \
    IMA_EVM_PRIVKEY IMA_EVM_X509 IMA_EVM_ROOT_CA \
    TACTIQ_FIT_KEY_DIR \
    TACTIQ_MODULE_SIG_KEY \
"

addhandler tactiq_keygate
tactiq_keygate[eventmask] = "bb.event.ConfigParsed"
python tactiq_keygate() {
    import os

    d = e.data
    keyring = d.getVar('TACTIQ_KEYRING')
    if keyring == 'dev':
        return

    layer = d.getVar('LAYERDIR_tactiq-os') or ''
    devdir = os.path.realpath(os.path.join(layer, 'pki', 'dev'))

    faults = []
    for var in (d.getVar('TACTIQ_KEYGATE_VARS') or '').split():
        val = d.getVar(var)
        if not val:
            faults.append('%s is not set' % var)
            continue
        path = os.path.realpath(val)
        if (path == devdir or path.startswith(devdir + os.sep)
                or os.path.basename(val) == 'module-signing-dev.pem'):
            faults.append('%s points into pki/dev/ (%s)' % (var, val))

    if faults:
        bb.fatal("TACTIQ_KEYRING is '%s', not 'dev', but development signing "
                 "material is still in use:\n  %s\nSet each of these in "
                 "local.conf or the CI environment to keys outside the tree "
                 "(pki/README.md)." % (keyring, '\n  '.join(faults)))
}
