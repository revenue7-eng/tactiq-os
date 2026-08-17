SUMMARY = "Generate /etc/fw_env.config for the boot medium in use"
DESCRIPTION = "The U-Boot environment lives in a raw window on the medium the \
system booted from. Rockchip U-Boot resolves that medium at runtime, so it \
cannot be hardcoded at build time. This oneshot service derives it from the \
block device carrying the mounted rootfs and writes /etc/fw_env.config before \
RAUC touches the environment."
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "file://tactiq-fw-env-setup.sh \
           file://tactiq-fw-env-setup.service"

S = "${WORKDIR}"

inherit systemd

SYSTEMD_SERVICE:${PN} = "tactiq-fw-env-setup.service"

RDEPENDS:${PN} = "libubootenv-bin"

do_install() {
    install -d ${D}/opt/tactiq/bin
    install -m 0755 ${UNPACKDIR}/tactiq-fw-env-setup.sh ${D}/opt/tactiq/bin/tactiq-fw-env-setup

    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${UNPACKDIR}/tactiq-fw-env-setup.service ${D}${systemd_system_unitdir}/tactiq-fw-env-setup.service
}

FILES:${PN} = "/opt/tactiq/bin/tactiq-fw-env-setup \
               ${systemd_system_unitdir}/tactiq-fw-env-setup.service"
