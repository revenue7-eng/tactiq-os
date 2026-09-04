# TactiQ OS — DEVELOPMENT image profile
# ============================================================================
# The production profile (`tactiq-image.bb`) is the base; this recipe requires
# it and adds bring-up conveniences: a passwordless root, an SSH server,
# SELinux policy management tooling, the audit daemon, TPM bring-up utilities
# and build-time IMA/EVM signing with the in-tree development key.
#
# Nothing declared here reaches production through inheritance: the require
# runs one way, dev -> production, and CI enforces that direction in both
# senses. That guarantee covers inheritance and nothing else. A package named
# above can still be present in production when something declared in the base
# pulls it in as an RDEPENDS -- `audit` and `tpm2-tools` are both such cases
# today. Whether a package ships in production is answered by the image
# manifest, not by this file.
#
# This profile is for bring-up only and is not a deployment artifact.
#
# Build: MACHINE=tactiq-rock5a bitbake tactiq-image-dev
# ============================================================================
SUMMARY = "TactiQ OS — development profile (debug-tweaks, SSH server)"

require tactiq-image.bb

# ---------------------------------------------------------------------------
# SSH server for bring-up and integration debugging
# ---------------------------------------------------------------------------
IMAGE_FEATURES += "ssh-server-openssh"
IMAGE_INSTALL:append = " \
    openssh-sshd \
    openssh-ssh \
    openssh-keygen \
"

# ---------------------------------------------------------------------------
# Root password
# ---------------------------------------------------------------------------
# Development debug feature set (passwordless/empty root, root login).
# Defined here and nowhere else: production never declares it, so there is no
# pair of definitions that can drift apart.
TACTIQ_DEBUG_FEATURES = "allow-empty-password allow-root-login empty-root-password post-install-logging"
EXTRA_IMAGE_FEATURES:append = " ${TACTIQ_DEBUG_FEATURES}"

# The base locks the root account through extrausers. Clear the parameter so
# the lock does not fight the debug feature set above; the class stays
# inherited but has nothing to apply.
EXTRA_USERS_PARAMS = ""

# ---------------------------------------------------------------------------
# SELinux policy management tooling
# ---------------------------------------------------------------------------
# semodule, sesearch and the python bindings are used for on-target policy
# debugging. The `policycoreutils` meta package hard-RDEPENDS selinux-python,
# which pulls setools and the whole python3 runtime — acceptable on a bench
# image, not on a device.
IMAGE_INSTALL:append = " \
    policycoreutils \
    policycoreutils-semodule \
    policycoreutils-hll \
    libselinux-python \
    libselinux-bin \
    checkpolicy \
"

# ---------------------------------------------------------------------------
# Audit daemon
# ---------------------------------------------------------------------------
# AVC denials are read from the audit log during policy work.
IMAGE_INSTALL:append = " audit"

# ---------------------------------------------------------------------------
# Bench utilities
# ---------------------------------------------------------------------------
IMAGE_INSTALL:append = " jq"

# ---------------------------------------------------------------------------
# Debug tools — enable per bring-up session, never in a release
# ---------------------------------------------------------------------------
# IMAGE_INSTALL:append = " strace tcpdump nano less"

# ---------------------------------------------------------------------------
# SBOM generation
# ---------------------------------------------------------------------------
INHERIT += "create-spdx"

# ---------------------------------------------------------------------------
# IMA/EVM rootfs signing (development profile only)
# ---------------------------------------------------------------------------
# Signs the whole rootfs at build time and installs the appraisal policy
# as /etc/ima/ima-policy. Keyed off the IMA_EVM_* variables, which are set
# in conf/distro/tactiq.conf against LAYERDIR_tactiq-os, so a clean
# checkout reproduces this. The signing key is the in-tree development one:
# it is applied here and the production base does not require this recipe,
# so it cannot reach a production image. Never built in CI.
IMAGE_INSTALL:append = " ima-evm-keys"
IMAGE_CLASSES += "ima-evm-rootfs"

# ima-evm-rootfs installs IMA_EVM_POLICY with a bare install(1), leaving
# /etc/ima/ima-policy at 0755. The kernel reads the file at init; the
# executable bit is meaningless and group/other have no reason to see it.
#
# The class appends ima_evm_sign_rootfs to IMAGE_PREPROCESS_COMMAND from a
# RecipePreFinalise handler specifically so that it runs last, which means a
# plain :append in this recipe would be ordered ahead of it and would chmod a
# file that does not exist yet. Append from a handler of our own instead: this
# recipe is parsed after the class, so our handler registers later and our
# command lands after theirs.
tactiq_ima_policy_mode() {
    if [ -f ${IMAGE_ROOTFS}${sysconfdir}/ima/ima-policy ]; then
        # Label first: /etc/ima and the policy file are created by
        # ima-evm-rootfs after the build-time setfiles pass, so they land
        # unlabeled and init cannot load the policy. The tactiq_ima module
        # maps /etc/ima(/.*)? to tactiq_ima_policy_t and grants init_t
        # read + system:policy_load on it (see AVC: class system,
        # policy_load is checked against the file label).
        setfiles -r ${IMAGE_ROOTFS} \
            ${IMAGE_ROOTFS}/etc/selinux/targeted/contexts/files/file_contexts \
            ${IMAGE_ROOTFS}${sysconfdir}/ima \
            ${IMAGE_ROOTFS}${sysconfdir}/ima/ima-policy

        chmod 0600 ${IMAGE_ROOTFS}${sysconfdir}/ima/ima-policy

        # Re-sign: the class signs with --portable, which covers mode and
        # security xattrs. Both the relabel and the chmod above invalidate
        # that signature, so redo it exactly as the class does.
        tmp="$(file ${IMAGE_ROOTFS}/lib/libc.so.6 | grep -o 'ELF .*-bit')"
        if [ "${tmp}" = "ELF 32-bit" ]; then
            evmctl_param="--m32"
    else
            evmctl_param=""
        fi
        export EVMCTL_KEY_PASSWORD=${IMA_EVM_EVMCTL_KEY_PASSWORD}
        evmctl sign --imasig ${evmctl_param} --portable -a sha256 \
            --key "${IMA_EVM_PRIVKEY}" ${IMA_EVM_PRIVKEY_KEYID_OPT} \
            "${IMAGE_ROOTFS}${sysconfdir}/ima/ima-policy"
    fi

    # /etc/fstab: read_only_rootfs_hook (read-only-rootfs in IMAGE_FEATURES,
    # rootfs-postcommands.bbclass) rewrites it with sed -i during do_rootfs.
    # sed -i replaces the inode, so the security.selinux xattr set by the
    # build-time setfiles pass is lost; ima_evm_sign_rootfs then signs the
    # unlabeled file. On target the generator gets Permission denied on
    # unlabeled_t, fstab is never parsed and the root stays rw. Relabel and
    # re-sign, same reasoning as the ima-policy block above; no chmod, the
    # packaged mode is already correct.
    if [ -f ${IMAGE_ROOTFS}${sysconfdir}/fstab ]; then
        setfiles -r ${IMAGE_ROOTFS} \
            ${IMAGE_ROOTFS}/etc/selinux/targeted/contexts/files/file_contexts \
            ${IMAGE_ROOTFS}${sysconfdir}/fstab

        tmp="$(file ${IMAGE_ROOTFS}/lib/libc.so.6 | grep -o 'ELF .*-bit')"
        if [ "${tmp}" = "ELF 32-bit" ]; then
            evmctl_param="--m32"
        else
            evmctl_param=""
        fi
        export EVMCTL_KEY_PASSWORD=${IMA_EVM_EVMCTL_KEY_PASSWORD}
        evmctl sign --imasig ${evmctl_param} --portable -a sha256 \
            --key "${IMA_EVM_PRIVKEY}" ${IMA_EVM_PRIVKEY_KEYID_OPT} \
            "${IMAGE_ROOTFS}${sysconfdir}/fstab"
    fi
}

# Run after do_image's body, which is where the class installs the policy
# and signs the rootfs; before do_image_<type> packs the filesystem. A
# static varflag, so unlike an event handler it lands in the basehash
# deterministically.
do_image[postfuncs] += "tactiq_ima_policy_mode"

# ---------------------------------------------------------------------------
# TPM bring-up tooling
# ---------------------------------------------------------------------------
# tpm2-tools for manual interaction during bring-up, and the mssim TCTI so
# the same image can talk to swtpm over the simulator socket. Production
# talks to /dev/tpmrm0 through libtss2-tcti-device, which the agent pulls in
# as an RDEPENDS.
IMAGE_INSTALL:append = " \
    tpm2-tools \
    libtss2-tcti-mssim \
"

# The ima-evm-rootfs class reads IMA_EVM_POLICY inside a shell function; without
# this varflag bitbake does not see content changes and ships a stale policy.
do_image[file-checksums] += "${IMA_EVM_POLICY}:True"
