# Development keyring: the RAUC trust root is the same pki/dev/ hierarchy
# used for kernel module signing. Its private keys are public by design
# (see pki/README.md), which is what makes the check reproducible from
# outside and what makes this root unfit for production.
FILESEXTRAPATHS:prepend := "${THISDIR}/files:${LAYERDIR_tactiq-os}/pki/dev:"

RAUC_KEYRING_FILE = "${@'root-ca.pem' if d.getVar('TACTIQ_KEYRING') == 'dev' else (d.getVar('RAUC_KEYRING_FILE_EXTERNAL') or '')}"

python () {
    if d.getVar('TACTIQ_KEYRING') != 'dev' and not d.getVar('RAUC_KEYRING_FILE_EXTERNAL'):
        bb.fatal("TACTIQ_KEYRING is '%s', not 'dev', but RAUC_KEYRING_FILE_EXTERNAL "
                 "is unset. A non-development build must supply its own keyring; "
                 "the in-tree pki/dev/ root must not ship in production images. "
                 "See RELEASE_INTEGRITY.md section 2.6."
                 % d.getVar('TACTIQ_KEYRING'))
}
