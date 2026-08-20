# TactiQ OS — DEVELOPMENT image profile
# ============================================================================
# This profile retains debug-tweaks (passwordless root, root-login over SSH)
# and an OpenSSH server for bring-up and integration debugging. It is NOT
# suitable for production deployments and is NEVER signed as a release
# artifact. The production profile is `tactiq-image.bb`; CI gates ensure
# tagged releases build from the production recipe.
#
# Build: MACHINE=tactiq-rock5a bitbake tactiq-image-dev
# ============================================================================
SUMMARY = "TactiQ OS — development profile (debug-tweaks, SSH server)"
LICENSE = "MIT"
inherit core-image
inherit selinux-image

# ---------------------------------------------------------------------------
# Base: core-image-minimal (no kernel-modules group!)
# ---------------------------------------------------------------------------
IMAGE_INSTALL:append = " \
    packagegroup-core-boot \
"

# ---------------------------------------------------------------------------
# Kernel modules: only what the runtime needs (instead of kernel-modules
# which pulls in all ~500 modules built for the kernel).
# ---------------------------------------------------------------------------
# Crypto — required for TPM, mTLS, dm-verity
IMAGE_INSTALL:append = " \
    kernel-module-af-alg \
    kernel-module-algif-rng \
"

# Netfilter — required for the iptables firewall
IMAGE_INSTALL:append = " \
    kernel-module-ip-tables \
    kernel-module-ip6-tables \
    kernel-module-iptable-filter \
    kernel-module-iptable-nat \
    kernel-module-iptable-mangle \
    kernel-module-nf-conntrack \
    kernel-module-nf-nat \
    kernel-module-nf-defrag-ipv4 \
    kernel-module-nf-defrag-ipv6 \
    kernel-module-nf-reject-ipv4 \
    kernel-module-x-tables \
    kernel-module-xt-conntrack \
    kernel-module-xt-state \
    kernel-module-xt-tcpudp \
"
# NOTE(wrynose/6.18): kernel-module-nfnetlink intentionally absent above —
# CONFIG_NETFILTER_NETLINK is builtin (=y) in the 6.18 linux-yocto config,
# so no module package is generated; nfnetlink is compiled into Image.

# System — watchdog, TUN (VPN), FUSE
IMAGE_INSTALL:append = " \
"

# IPsec — placeholder for VPN modules if a deployment requires them
IMAGE_INSTALL:append = " \
"

# ---------------------------------------------------------------------------
# Networking (required for mTLS attestation)
# ---------------------------------------------------------------------------
IMAGE_INSTALL:append = " \
    openssh-sshd \
    openssh-ssh \
    openssh-keygen \
    openssl \
    openssl-bin \
    ca-certificates \
    chrony \
    iproute2 \
    iptables \
"

# ---------------------------------------------------------------------------
# TactiQ components
# ---------------------------------------------------------------------------
IMAGE_INSTALL:append = " \
    tactiq-agent \
    tactiq-config \
    tactiq-release \
    agentgateway \
    agentgateway-config \
"

# ---------------------------------------------------------------------------
# OTA Updates (RAUC A/B)
# ---------------------------------------------------------------------------
IMAGE_INSTALL:append = " rauc"

# Generates /etc/fw_env.config for the boot medium in use; RAUC cannot mark
# a slot good without it. See recipes-bsp/tactiq-fw-env.
IMAGE_INSTALL:append = " tactiq-fw-env"

# ---------------------------------------------------------------------------
# System utilities — minimal set
# ---------------------------------------------------------------------------
IMAGE_INSTALL:append = " \
    bash \
    curl \
    jq \
    procps \
"

# util-linux: install only the binaries the runtime uses, not the full
# package (~80 utilities).
IMAGE_INSTALL:append = " \
    util-linux-mount \
    util-linux-umount \
    util-linux-blkid \
    util-linux-lsblk \
    util-linux-findmnt \
    util-linux-dmesg \
    util-linux-hwclock \
    util-linux-losetup \
    util-linux-flock \
    util-linux-nsenter \
    util-linux-unshare \
    util-linux-agetty \
    util-linux-sulogin \
    util-linux-switch-root \
    util-linux-fsck \
    util-linux-fdisk \
"

# ---------------------------------------------------------------------------
# Security: SELinux + audit
# ---------------------------------------------------------------------------
IMAGE_INSTALL:append = " \
    libselinux \
    libselinux-python \
    policycoreutils \
    policycoreutils-setfiles \
    policycoreutils-semodule \
    policycoreutils-sestatus \
    checkpolicy \
    policycoreutils-hll \
    libselinux-bin \
    selinux-autorelabel \
    refpolicy-targeted \
    audit \
"

# ---------------------------------------------------------------------------
# Boot infrastructure — kernel devicetree blobs in rootfs /boot/
# ---------------------------------------------------------------------------
# extlinux loads the FDT from a path inside the rootfs (FDT = /boot/<dtb>).
# Without kernel-devicetree in IMAGE_INSTALL the .dtb files are deployed
# only to the boot_a FAT partition via IMAGE_BOOT_FILES (wic mechanism)
# and are absent from the rootfs, which causes extlinux to fail FDT load.
IMAGE_INSTALL:append = " kernel-devicetree"
# setools and selinux-python are kept for the development phase.
# Production can drop them (saves ~50MB of Python).

# ---------------------------------------------------------------------------
# Debug tools — REMOVE BEFORE PRODUCTION
# ---------------------------------------------------------------------------
# IMAGE_INSTALL:append = " strace tcpdump nano less"

# ---------------------------------------------------------------------------
# Image features
# ---------------------------------------------------------------------------
IMAGE_FEATURES += "ssh-server-openssh"
IMAGE_FEATURES += "read-only-rootfs"
# package-management is dropped — opkg is not useful on a read-only rootfs.

# ---------------------------------------------------------------------------
# Disk space — trimmed
# ---------------------------------------------------------------------------
IMAGE_ROOTFS_EXTRA_SPACE = "65536"
IMAGE_OVERHEAD_FACTOR = "1.15"
# Was: 524288 (512MB headroom). Now: 65536 (64MB) — enough for logs.

# ---------------------------------------------------------------------------
# Root password (CHANGE IN PRODUCTION)
# ---------------------------------------------------------------------------
# Development debug feature set (passwordless/empty root, root login).
# Defined once here; the production profile removes exactly this set by
# referencing ${TACTIQ_DEBUG_FEATURES}, so the two cannot drift apart.
TACTIQ_DEBUG_FEATURES = "allow-empty-password allow-root-login empty-root-password post-install-logging"
EXTRA_IMAGE_FEATURES:append = " ${TACTIQ_DEBUG_FEATURES}"

# ---------------------------------------------------------------------------
# SBOM generation
# ---------------------------------------------------------------------------
INHERIT += "create-spdx"

# ---------------------------------------------------------------------------
# IMA/EVM rootfs signing (measurement/dev profile only)
# ---------------------------------------------------------------------------
# Signs the whole rootfs at build time and installs the appraisal policy
# as /etc/ima/ima-policy. Keyed off the IMA_EVM_* variables, which are set
# in conf/distro/tactiq.conf against LAYERDIR_tactiq-os, so a clean
# checkout reproduces this. Applied here and not in tactiq-image.bb: the
# signing key is the in-tree development one and must not reach a
# production image. Never built in CI.
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
}

# Run after do_image's body, which is where the class installs the policy
# and signs the rootfs; before do_image_<type> packs the filesystem. A
# static varflag, so unlike an event handler it lands in the basehash
# deterministically.
do_image[postfuncs] += "tactiq_ima_policy_mode"

# ---------------------------------------------------------------------------
# TPM bring-up tooling (dev profile only)
# ---------------------------------------------------------------------------
# tpm2-tools for manual interaction during bring-up, and the mssim TCTI so
# the same image can talk to swtpm over the simulator socket. Neither ships
# in the production profile: production talks to /dev/tpmrm0 through
# libtss2-tcti-device, which the agent pulls in as an RDEPENDS.
IMAGE_INSTALL:append = " \
    tpm2-tools \
    libtss2-tcti-mssim \
"
