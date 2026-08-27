# TactiQ OS — PRODUCTION image profile (base)
# ============================================================================
# This recipe is the base of the image family. It defines the component set
# that ships to a device: no interactive login path, no SSH server, no policy
# management tooling, no bring-up utilities.
#
# The development profile (`tactiq-image-dev.bb`) requires this file and adds
# to it. A component present here reaches both profiles; a component present
# only in the development recipe cannot reach production by omission. This is
# the inverse of the previous arrangement, where production was derived from
# the development profile by removal and any forgotten `:remove` shipped a
# development component to a device.
#
# Build: MACHINE=tactiq-rock5a bitbake tactiq-image
# ============================================================================
SUMMARY = "TactiQ OS — production profile"
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
# NOTE(6.18): kernel-module-nfnetlink intentionally absent above —
# CONFIG_NETFILTER_NETLINK is builtin (=y) in the 6.18 linux-yocto config,
# so no module package is generated; nfnetlink is compiled into Image.

# ---------------------------------------------------------------------------
# Networking (required for mTLS attestation)
# ---------------------------------------------------------------------------
# No SSH server: the development profile adds one. A production image has no
# interactive login path.
IMAGE_INSTALL:append = " \
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
# Security: SELinux runtime
#
# Enforcement needs libselinux (C) and the loaded policy. Relabeling of the
# empty /data partition on first boot needs setfiles, which is the only
# RDEPENDS of selinux-autorelabel. Policy management tooling (semodule,
# sesearch, semanage) is not required at runtime and ships only in the
# development profile: the full `policycoreutils` meta package hard-RDEPENDS
# selinux-python, which pulls setools and the whole python3 runtime.
#
# selinux-autorelabel is installed in NEITHER profile: runtime relabeling of
# the root filesystem does not exist on this system by design. The rootfs is
# labeled at build time; a bulk relabel would rewrite security.selinux
# everywhere and invalidate every EVM portable signature.
#
# audit ships in this profile and is not removable: it is an RDEPENDS of
# dbus-1, shadow-base, libsemanage2 and policycoreutils-setfiles. Verified
# 27.08.2026 against buildhistory depends.dot. This is accepted rather than
# worked around — SELinux runs in enforcing mode, and without auditd an AVC
# denial goes to the kernel ring buffer and is lost on reboot, which
# contradicts the immutable-logging property the product claims. Do not
# attempt to strip it; removing setfiles breaks /data labelling on first boot.
#
# NOT ESTABLISHED: that auditd is configured for this platform — rule set,
# log persistence across reboot, flash wear bounds. Package presence in the
# manifest is not a working audit subsystem. External claims about logging
# must not rely on this line.
# ---------------------------------------------------------------------------
IMAGE_INSTALL:append = " \
    libselinux \
    policycoreutils-setfiles \
    policycoreutils-sestatus \
    refpolicy-targeted \
"

# ---------------------------------------------------------------------------
# Boot infrastructure — kernel devicetree blobs in rootfs /boot/
# ---------------------------------------------------------------------------
# extlinux loads the FDT from a path inside the rootfs (FDT = /boot/<dtb>).
# Without kernel-devicetree in IMAGE_INSTALL the .dtb files are deployed
# only to the boot_a FAT partition via IMAGE_BOOT_FILES (wic mechanism)
# and are absent from the rootfs, which causes extlinux to fail FDT load.
IMAGE_INSTALL:append = " kernel-devicetree"

# ---------------------------------------------------------------------------
# Image features
# ---------------------------------------------------------------------------
IMAGE_FEATURES += "read-only-rootfs"
# package-management is dropped — opkg is not useful on a read-only rootfs.
# ssh-server-openssh is added by the development profile only.

# ---------------------------------------------------------------------------
# Disk space — trimmed
# ---------------------------------------------------------------------------
IMAGE_ROOTFS_EXTRA_SPACE = "65536"
IMAGE_OVERHEAD_FACTOR = "1.15"

# ---------------------------------------------------------------------------
# Root account is locked
# ---------------------------------------------------------------------------
# The agent and its services run under their SELinux domains; there is no
# interactive root login path on a production image. The account is locked by
# setting an invalid password hash via the extrausers class.
#
# `inherit`, not `INHERIT +=`: INHERIT is resolved at configuration parse
# time. Written inside a recipe it adds the name to the list, but the class
# body never runs, so the `ROOTFS_POSTPROCESS_COMMAND += "set_user_group"`
# in extrausers.bbclass never takes effect and the account is not locked.
# Verify with:
#   bitbake-getvar -r tactiq-image --value ROOTFS_POSTPROCESS_COMMAND
# set_user_group must appear in the output.
inherit extrausers
EXTRA_USERS_PARAMS = "usermod -p '!' root;"

# ---------------------------------------------------------------------------
# Runtime-unneeded leaf packages (no in-image hard-RDEPENDS)
# ---------------------------------------------------------------------------
PACKAGE_EXCLUDE += "shared-mime-info libxml2"
