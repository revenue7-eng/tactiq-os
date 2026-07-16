FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

SRC_URI += "file://fw_env.config"

# Полный дефолтный env генерируется рецептом u-boot-rockchip (do_deploy).
# Дописываем поверх него RAUC-переменные слотов A/B.
do_install:append() {
    install -d ${D}${sysconfdir}
    install -m 0644 ${UNPACKDIR}/fw_env.config ${D}${sysconfdir}/fw_env.config

    install -m 0644 ${DEPLOY_DIR_IMAGE}/u-boot-initial-env ${D}${sysconfdir}/u-boot-initial-env
    cat >> ${D}${sysconfdir}/u-boot-initial-env << 'ENVEOF'
BOOT_ORDER=A B
BOOT_A_LEFT=3
BOOT_B_LEFT=3
ENVEOF
}

do_install[depends] += "u-boot-rockchip:do_deploy"

FILES:${PN} += "${sysconfdir}/fw_env.config ${sysconfdir}/u-boot-initial-env"
