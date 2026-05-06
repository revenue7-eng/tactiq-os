# Override git fetch with tarball — git.kernel.org/github unreachable from WSL (RU geo-block).
# Tarball downloaded manually to Windows Downloads, served via own-mirrors.

SRC_URI = "https://github.com/erofs/erofs-utils/archive/refs/tags/v${PV}.tar.gz;downloadfilename=erofs-utils-${PV}.tar.gz"
SRC_URI[sha256sum] = "196083d63e5e231fb5799e7ce86a944bbca564daabce3de9225a8aca9dcaff15"

S = "${WORKDIR}/erofs-utils-${PV}"

SRCREV = ""
SRCREV:class-native = ""
