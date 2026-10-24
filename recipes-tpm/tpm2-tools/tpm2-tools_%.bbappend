# tpm2-tools links libcurl into its single tpm2 binary for one tool,
# tpm2_getekcertificate, which fetches an EK certificate from the TPM vendor
# over HTTP. The device has no network role, so that tool and the library are
# left out of the target package. The native tools are unchanged.
#
# tpm2-tools is in the image because the attestation agent reaches the TPM
# through it (tactiq-agent RDEPENDS). When the agent moves to tss-esapi,
# tpm2-tools leaves the production image and this append can go with it.
# The :tactiq override limits this to the TactiQ distro: a distro that
# reuses this layer keeps the upstream behaviour.
FILESEXTRAPATHS:prepend:tactiq := "${THISDIR}/files:"
DEPENDS:remove:class-target:tactiq = "curl"
SRC_URI:append:class-target:tactiq = " file://0001-drop-tpm2_getekcertificate-and-the-libcurl-dependency.patch"
