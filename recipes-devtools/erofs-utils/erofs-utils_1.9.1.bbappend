# Override git fetch with tarball — git.kernel.org unreachable from WSL (RU geo-block).
# Tarball downloaded manually to Windows Downloads, served via own-mirrors (TACTIQ_MIRROR).
# Upstream: kernel.org cgit snapshot (NOT github.com/erofs/erofs-utils — that repo has no releases).
SRC_URI = "https://git.kernel.org/pub/scm/linux/kernel/git/xiang/erofs-utils.git/snapshot/erofs-utils-${PV}.tar.gz"
SRC_URI[sha256sum] = "a9ef5ab67c4b8d2d3e9ed71f39cd008bda653142a720d8a395a36f1110d0c432"

# wrynose: S under ${WORKDIR} is forbidden; use UNPACKDIR for unpacked sources.
UNPACKDIR = "${WORKDIR}/sources"
S = "${UNPACKDIR}/erofs-utils-${PV}"

SRCREV = ""
SRCREV:class-native = ""
