# bbappend for linux-rockchip (used by tactiq-rock5b machine).
#
# meta-rockchip ships its own kernel recipe (linux-rockchip) on most
# scarthgap-era branches; the linux-yocto bbappend in the parent
# directory does not apply to it. Mirror the security fragment here so
# that the rock5b machine receives the same hardening as the linux-yocto
# based machines.
#
# The shared fragment lives under linux-yocto/tactiq-security.cfg and is
# referenced from this bbappend by file:// path so a single source of
# truth is preserved.

FILESEXTRAPATHS:prepend := "${THISDIR}/linux-yocto:"
SRC_URI += "file://tactiq-security.cfg"

# Pin linux-rockchip to the same 6.6 LTS point-release series as
# linux-yocto. Review this pin together with a CVE scan before bumping.
PREFERRED_VERSION_linux-rockchip = "6.6%"
