# Override git fetch with tarball — git.kernel.org unreachable from WSL (RU geo-block).
# Tarball downloaded manually to Windows Downloads, served via own-mirrors (TACTIQ_MIRROR).
SRC_URI = "https://www.kernel.org/pub/linux/kernel/people/kdave/btrfs-progs/btrfs-progs-v${PV}.tar.xz"
SRC_URI[sha256sum] = "bb27e1ec54e7c3c0b7b2e596f853a73c07a3d72f21bc94042073c24dbf045796"

# wrynose: S under ${WORKDIR} is forbidden; use UNPACKDIR for unpacked sources.
UNPACKDIR = "${WORKDIR}/sources"
S = "${UNPACKDIR}/btrfs-progs-v${PV}"

SRCREV = ""
SRCREV:class-native = ""
