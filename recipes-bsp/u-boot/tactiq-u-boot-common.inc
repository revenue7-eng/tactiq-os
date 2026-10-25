# Board-independent U-Boot patches for TactiQ OS.
#
# A board recipe requires this file as its last line, so these patches apply
# after the board's own. They touch generic code only (boot/, include/, lib/)
# and apply to a pristine v2026.10 tree on their own, without any board patch.
#
# 0007: the TCG2 code tests SM3 per build phase, so an SPL that links the
#       TCG2 code does not need SM3.
# 0008: lock the TPM platform hierarchy before starting the OS
#       (CONFIG_MEASURED_BOOT_LOCK_PLATFORM). The config fragment that turns
#       it on, tpm-lock.cfg, stays in the board layer for now.
#
# The file names keep their numbers from the board series they came from.

FILESEXTRAPATHS:prepend := "${THISDIR}/u-boot-common:"

SRC_URI += "file://0007-tpm-tcg2-gate-SM3-per-build-phase.patch \
            file://0008-boot-lock-the-TPM-platform-hierarchy-before-the-OS.patch"
