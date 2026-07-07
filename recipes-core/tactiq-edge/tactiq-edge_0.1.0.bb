SUMMARY = "TactiQ Edge inference core and reference CLI"
DESCRIPTION = "Model-agnostic TensorFlow Lite inference engine (Layer 2 of \
the TactiQ stack) plus a minimal reference client that runs one preprocessed \
frame through a model to a class verdict."
LICENSE = "CLOSED"

# Release source of truth. This is DORMANT during development: local.conf
# enables externalsrc:pn-tactiq-edge to build straight from the working tree.
# For a reproducible product build, drop the externalsrc override and pin
# SRCREV to a released commit.
SRC_URI = "git:///mnt/d/tactiq-edge;protocol=file;branch=main"
SRCREV = "${AUTOREV}"
# Do NOT set S = "${WORKDIR}/git" — the wrynose fetch/unpack schema changed and
# setting it explicitly breaks do_unpack (same fix as agentgateway). Rely on
# the series default. Under externalsrc, S is the working tree anyway.

DEPENDS = "libtensorflow-lite flatbuffers"

inherit cmake

# XNNPACK is the fast CPU path on aarch64 (RK3588S) — the measured product
# path for classification. Matches the tensorflow-lite layer's own examples.
EXTRA_OECMAKE:append:aarch64 = " -DTFLITE_ENABLE_XNNPACK=ON"

FILES:${PN} += "${bindir}/tactiq-edge-cli ${bindir}/tactiq-edge-daemon ${bindir}/tactiq-edge-probe ${bindir}/tactiq-edge-v4l2-probe"
