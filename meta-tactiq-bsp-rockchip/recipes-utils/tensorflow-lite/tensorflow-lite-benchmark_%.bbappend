# Bake-in quant model for NPU benchmarking — measurement setup, not product.
# Makes the measurement image self-contained and reproducible: a reproducer
# builds from git and gets the quant model in the image at a deterministic
# path, with no manual cp onto a mounted ext4 (removes the recurring manual
# step and the SELinux-label issue — the file goes through standard rootfs
# labeling).
#
# Provenance: canonical upstream release mobilenet_v1_2018_08_02 (quant).
# Differs from the float release 2018_02_22 pulled by the base recipe —
# these are two distinct mobilenet releases, see the measurements artifact.
#   tarball  sha256 = d32432d28673a936b2d6281ab0600c71cf7226dfe4cdcef3012555f691744166
#   .tflite  sha256 = ecc3a67c47c5a609ec35f6a58a7d97532834e43df4cb7d3f1204a8164b7d20dd (4276352 bytes)
SRC_URI += "https://storage.googleapis.com/download.tensorflow.org/models/mobilenet_v1_2018_08_02/mobilenet_v1_1.0_224_quant.tgz;name=quantmodel"
SRC_URI[quantmodel.sha256sum] = "d32432d28673a936b2d6281ab0600c71cf7226dfe4cdcef3012555f691744166"
do_install:append() {
    install -m 644 ${UNPACKDIR}/mobilenet_v1_1.0_224_quant.tflite \
        ${D}${datadir}/tensorflow/lite/tools/benchmark/mobilenet_v1_1.0_224_quant.tflite
}
