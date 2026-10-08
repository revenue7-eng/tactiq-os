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

# Version limits, see system.conf: the bundle manifest version and the
# device's min-bundle-version both come from release-rev.inc.
require recipes-core/tactiq-release/release-derived.inc

# prevent-late-fallback is on unless a development build turns it off in its
# own local.conf (to keep the other slot as a bench fallback). Not allowed
# with a non-development keyring.
TACTIQ_RAUC_ALLOW_LATE_FALLBACK ??= "0"
do_install[vardeps] += "TACTIQ_RAUC_VERSION TACTIQ_RAUC_ALLOW_LATE_FALLBACK"

python () {
    if d.getVar('TACTIQ_RAUC_ALLOW_LATE_FALLBACK') == '1' and d.getVar('TACTIQ_KEYRING') != 'dev':
        bb.fatal("TACTIQ_RAUC_ALLOW_LATE_FALLBACK=1 is for development keyrings only")
}

do_install:append() {
    conf=${D}${sysconfdir}/rauc/system.conf
    [ -f "$conf" ] || bbfatal "system.conf not installed at $conf"
    sed -i -e "s|@TACTIQ_RAUC_VERSION@|${TACTIQ_RAUC_VERSION}|" "$conf"
    if [ "${TACTIQ_RAUC_ALLOW_LATE_FALLBACK}" = "1" ]; then
        sed -i -e '/^prevent-late-fallback=true$/d' "$conf"
    fi
    grep -q "^min-bundle-version=${TACTIQ_RAUC_VERSION}$" "$conf" || \
        bbfatal "min-bundle-version not set in $conf"
    ! grep -q "@TACTIQ_" "$conf" || bbfatal "unresolved placeholder in $conf"
}

# Rock 5T: its own compatible string, so RAUC on a 5T refuses a Rock 5A
# bundle and the other way round. Override only: the Rock 5A task is not
# touched.
do_install:append:tactiq-rock5t() {
    conf=${D}${sysconfdir}/rauc/system.conf
    sed -i -e 's|^compatible=TactiQ OS Rock5A$|compatible=TactiQ OS Rock5T|' "$conf"
    grep -q '^compatible=TactiQ OS Rock5T$' "$conf" || \
        bbfatal "RAUC compatible is not set for the Rock 5T in $conf"
}
