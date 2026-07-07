SUMMARY = "TactiQ Edge smoke test (throwaway)"
DESCRIPTION = "Disposable bring-up scaffold: runs tactiq-edge-cli once at boot, writes predicted class to /data/tactiq/edge-smoketest.txt. NOT a product component, NOT the AgriBox cartridge. Remove after the fact is captured."
LICENSE = "CLOSED"

inherit systemd

RDEPENDS:${PN} = "tactiq-edge"

SRC_URI = " \
    file://edge-smoketest.service \
    file://planthealth_cls_int8.tflite \
    file://frame0.bin \
    file://class_names.txt \
"

do_install() {
    install -d ${D}/usr/share/edge-smoketest
    install -m 0644 ${UNPACKDIR}/planthealth_cls_int8.tflite ${D}/usr/share/edge-smoketest/
    install -m 0644 ${UNPACKDIR}/frame0.bin ${D}/usr/share/edge-smoketest/
    install -m 0644 ${UNPACKDIR}/class_names.txt ${D}/usr/share/edge-smoketest/
    install -d ${D}${systemd_unitdir}/system
    install -m 0644 ${UNPACKDIR}/edge-smoketest.service ${D}${systemd_unitdir}/system/
}

SYSTEMD_SERVICE:${PN} = "edge-smoketest.service"
SYSTEMD_AUTO_ENABLE = "enable"

FILES:${PN} = " \
    /usr/share/edge-smoketest \
    ${systemd_unitdir}/system/edge-smoketest.service \
"
