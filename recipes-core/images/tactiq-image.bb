# TactiQ OS Image Recipe — OPTIMIZED
# ============================================================================
# Оптимизирован для минимального размера при сохранении полного security стека.
# Оригинал сохранён в backups/
# ============================================================================
SUMMARY = "TactiQ OS - Secure Edge Computing Platform"
LICENSE = "MIT"
inherit core-image
inherit selinux-image

# ---------------------------------------------------------------------------
# Base: core-image-minimal (без kernel-modules!)
# ---------------------------------------------------------------------------
IMAGE_INSTALL:append = " \
    packagegroup-core-boot \
"

# ---------------------------------------------------------------------------
# Kernel modules: ТОЛЬКО нужные (вместо kernel-modules который тянет ВСЕ ~500)
# ---------------------------------------------------------------------------
# Crypto — для TPM, mTLS, dm-verity
IMAGE_INSTALL:append = " \
    kernel-module-af-alg \
    kernel-module-algif-rng \
"

# Netfilter — для iptables firewall
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
    kernel-module-nfnetlink \
    kernel-module-x-tables \
    kernel-module-xt-conntrack \
    kernel-module-xt-state \
    kernel-module-xt-tcpudp \
"

# System — watchdog, TUN (VPN), FUSE
IMAGE_INSTALL:append = " \
"

# IPsec — для VPN если понадобится
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
"

# ---------------------------------------------------------------------------
# OTA Updates (RAUC A/B)
# ---------------------------------------------------------------------------
IMAGE_INSTALL:append = " rauc"

# ---------------------------------------------------------------------------
# System utilities — МИНИМАЛЬНЫЙ набор
# ---------------------------------------------------------------------------
IMAGE_INSTALL:append = " \
    bash \
    curl \
    jq \
    procps \
"

# util-linux: только нужные утилиты (вместо полного пакета ~80 утилит)
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
    selinux-autorelabel \
    refpolicy-targeted \
    audit \
"
# setools и selinux-python оставляем пока для dev-фазы
# В production можно убрать (сэкономит ~50MB Python)

# ---------------------------------------------------------------------------
# Debug tools — УБРАТЬ ПЕРЕД PRODUCTION
# ---------------------------------------------------------------------------
# IMAGE_INSTALL:append = " strace tcpdump nano less"

# ---------------------------------------------------------------------------
# Image features
# ---------------------------------------------------------------------------
IMAGE_FEATURES += "ssh-server-openssh"
IMAGE_FEATURES += "read-only-rootfs"
# Убран package-management — на read-only rootfs opkg бесполезен

# ---------------------------------------------------------------------------
# Disk space — убран лишний запас
# ---------------------------------------------------------------------------
IMAGE_ROOTFS_EXTRA_SPACE = "65536"
IMAGE_OVERHEAD_FACTOR = "1.15"
# Было: 524288 (512MB запаса!) Стало: 65536 (64MB) — достаточно для логов

# ---------------------------------------------------------------------------
# Root password (CHANGE IN PRODUCTION)
# ---------------------------------------------------------------------------
EXTRA_IMAGE_FEATURES:append = " debug-tweaks"

# ---------------------------------------------------------------------------
# SBOM generation
# ---------------------------------------------------------------------------
INHERIT += "create-spdx"
