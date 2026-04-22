FILESEXTRAPATHS:prepend := "${THISDIR}/${PN}:"
SRC_URI += "file://tactiq-security.cfg"

# ---------------------------------------------------------------------------
# Supply-chain pinning (SLSA L2 posture)
# ---------------------------------------------------------------------------
# Pin linux-yocto to an exact LTS point release series instead of the "6.6%"
# rolling wildcard so two independent builds resolve to the same kernel tree.
# Review this pin together with a CVE scan before bumping.
PREFERRED_VERSION_linux-yocto = "6.6.66%"

# TODO(slsa-l2): Add explicit SRCREV_machine / SRCREV_meta pins once the first
# reproducible image is archived with hashes captured from the reference
# scarthgap build. Tracking: internal issue "supply-chain pinning".
