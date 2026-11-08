# Rollback index in every configuration of the kernel FIT.
#
# U-Boot refuses a configuration whose "rollback-index" is below the floor in
# the TPM (CONFIG_FIT_ROLLBACK_TPM, patch 0010 in recipes-bsp/u-boot). The
# property sits inside the configuration node, which the configuration
# signature covers, so it is added before the image is signed for the last
# time: the FIT generator in oe-core has no hook for extra configuration
# properties, so the assembled and signed image gets the property with fdtput
# and is signed again with mkimage -F, with the key and options the class used.
#
# A separate function run as a postfunc of do_compile, not do_compile:append:
# an append is pasted into the class's own function body, where an import
# would shadow names the class uses before it.
#
# The value comes from release-rev.inc and travels with the tag.

require recipes-core/tactiq-release/release-rev.inc

do_compile[postfuncs] += "tactiq_fit_rollback_index"
do_compile[vardeps] += "tactiq_fit_rollback_index TACTIQ_ROLLBACK_INDEX"

python tactiq_fit_rollback_index() {
    import os
    import shlex
    import subprocess

    index = d.getVar('TACTIQ_ROLLBACK_INDEX')
    if not index.isdigit() or int(index) > 64:
        bb.fatal("TACTIQ_ROLLBACK_INDEX is '%s', not an integer from 0 to 64" % index)

    fit = os.path.join(d.getVar('B'), 'fitImage')
    if not os.path.exists(fit):
        bb.fatal("no FIT at %s" % fit)

    def run(cmd):
        try:
            return subprocess.run(cmd, check=True, capture_output=True).stdout.decode()
        except subprocess.CalledProcessError as e:
            bb.fatal("'%s' failed: %s" % (' '.join(cmd), e.stderr.decode()))

    confs = run(['fdtget', '-l', fit, '/configurations']).split()
    if not confs:
        bb.fatal("no configuration in %s" % fit)
    for conf in confs:
        run(['fdtput', '-t', 'u', fit, '/configurations/' + conf, 'rollback-index', index])

    if oe.types.boolean(d.getVar('FIT_KERNEL_SIGN_ENABLE')):
        cmd = [d.getVar('UBOOT_MKIMAGE_SIGN'), '-F', '-k', d.getVar('FIT_KERNEL_SIGN_KEYDIR'), '-r', fit]
        if d.getVar('UBOOT_MKIMAGE_DTCOPTS'):
            cmd.extend(['-D', d.getVar('UBOOT_MKIMAGE_DTCOPTS')])
        if d.getVar('UBOOT_MKIMAGE_SIGN_ARGS'):
            cmd.extend(shlex.split(d.getVar('UBOOT_MKIMAGE_SIGN_ARGS')))
        run(cmd)

    for conf in confs:
        got = run(['fdtget', '-t', 'u', fit, '/configurations/' + conf, 'rollback-index']).strip()
        if got != index:
            bb.fatal("rollback-index of %s reads '%s', expected '%s'" % (conf, got, index))
    bb.note("rollback-index %s in %s" % (index, ', '.join(confs)))
}
