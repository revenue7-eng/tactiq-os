# TactiQ OS — NPU bring-up image (DEV-based, NEVER released)
# ============================================================================
# Build: MACHINE=tactiq-rock5a-npu bitbake tactiq-image-npu
#
# STEP-1 SCOPE: prove rocket driver bind + /dev/accel/accel0 on hardware.
# accel0 is created by the KERNEL on probe — no userspace/mesa needed here.
#   kernel-module-rocket: places rocket.ko in rootfs. Dev image does NOT pull
#   the kernel-modules group, so without this modprobe rocket = false negative.
#
# DEFERRED TO STEP-4 (Teflon inference) — do NOT add here:
#   libteflon → mesa, which is SKIPPED unless one of opengl/vulkan/opencl is in
#   DISTRO_FEATURES. Our distro (tactiq.conf line 49) DELIBERATELY removes
#   opengl/vulkan as a hardening decision. Clean fix when we get there: drop
#   opengl from that remove-list + DISTRO_FEATURES:append:npu = " opengl"
#   (machine-scoped, release unaffected). This touches production hardening
#   posture → co-founder decision, made only after accel0 is proven.
# ============================================================================
require tactiq-image-dev.bb
SUMMARY = "TactiQ OS — NPU bring-up profile (dev-based, never released)"
IMAGE_INSTALL:append = " kernel-module-rocket tensorflow-lite-benchmark libteflon kernel-module-rockchip-thermal"
