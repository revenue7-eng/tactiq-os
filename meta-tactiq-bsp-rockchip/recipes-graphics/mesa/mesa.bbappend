# TactiQ OS — Mesa NPU userspace (NPU-build ONLY, scoped to "npu" override).
#
# Enables the Teflon TFLite delegate and the "rocket" gallium driver
# (Rockchip NPU) so libteflon.so can offload inference to the mainline
# rocket accel device. Fires only for MACHINE=tactiq-rock5a-npu; the
# hardened release machine lacks the "npu" token, so release mesa is
# unchanged.
#
# PACKAGECONFIG[teflon] / [rocket] already exist in oe-core mesa.inc
# (wrynose). rocket auto-adds itself to GALLIUMDRIVERS when enabled.
# The libteflon.so lands in the separate "libteflon" package, pulled
# into the NPU image via IMAGE_INSTALL.
PACKAGECONFIG:append:npu = " teflon rocket"
