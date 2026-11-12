SUMMARY = "IMA policy of the release image: measurement rules only"
DESCRIPTION = "Installs /etc/ima/ima-policy with the measurement rules of \
the development policy and no appraise rule. systemd loads the file at boot \
(the same path the development image uses), so execution, libraries, kernel \
modules and the reads of delivered data are measured into PCR 10, 11 and 12 \
as on the development image. Nothing is appraised: a release image carries \
no IMA signatures. Pulled in by tactiq-image.bb only for an image without \
ima-evm-rootfs, which installs its own policy."
HOMEPAGE = "https://github.com/revenue7-eng/tactiq-os"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"
SPDX_PACKAGE_SUPPLIER_ref = "SPDX_SUPPLIER_tactiq"

SRC_URI = "file://tactiq-ima-measure.policy"
S = "${UNPACKDIR}"

INHIBIT_DEFAULT_DEPS = "1"
ALLOW_EMPTY:${PN} = "0"
inherit allarch

do_configure[noexec] = "1"
do_compile[noexec] = "1"

# 0600, as the development image leaves its policy (tactiq-image-dev.bb,
# tactiq_ima_policy_mode): init reads it once, nobody else has a reason to.
# The label (tactiq_ima_policy_t, tactiq_ima.fc in tactiq-os-selinux) is set
# by the build-time setfiles pass like every packaged file; init_t is allowed
# to read it and to load it as policy.
do_install() {
    install -d -m 0755 ${D}${sysconfdir}/ima
    install -m 0600 ${S}/tactiq-ima-measure.policy ${D}${sysconfdir}/ima/ima-policy
}

FILES:${PN} = "${sysconfdir}/ima/ima-policy"
