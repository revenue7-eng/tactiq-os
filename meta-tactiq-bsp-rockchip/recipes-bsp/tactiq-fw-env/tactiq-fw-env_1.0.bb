SUMMARY = "Generate the fw_env.config for the boot medium in use"
DESCRIPTION = "The U-Boot environment lives in a raw window on the medium the \
system booted from. Rockchip U-Boot resolves that medium at runtime, so it \
cannot be hardcoded at build time. This oneshot service derives it from the \
block device carrying the mounted rootfs and writes it to /run/tactiq before \
RAUC touches the environment."
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "file://tactiq-fw-env-setup.sh \
           file://tactiq-fw-env-setup.service"

inherit systemd

SYSTEMD_SERVICE:${PN} = "tactiq-fw-env-setup.service"

RDEPENDS:${PN} = "libubootenv-bin"

do_install() {
    install -d ${D}/opt/tactiq/bin
    install -m 0755 ${UNPACKDIR}/tactiq-fw-env-setup.sh ${D}/opt/tactiq/bin/tactiq-fw-env-setup

    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${UNPACKDIR}/tactiq-fw-env-setup.service ${D}${systemd_system_unitdir}/tactiq-fw-env-setup.service

    # The rootfs is read-only in the target configuration, so the generated
    # config lives on tmpfs. This symlink keeps the canonical path working for
    # fw_setenv/fw_printenv and RAUC without passing -c.
    install -d ${D}${sysconfdir}
    ln -sf /run/tactiq/fw_env.config ${D}${sysconfdir}/fw_env.config
}

FILES:${PN} = "${sysconfdir}/fw_env.config \
               /opt/tactiq/bin/tactiq-fw-env-setup \
               ${systemd_system_unitdir}/tactiq-fw-env-setup.service"
