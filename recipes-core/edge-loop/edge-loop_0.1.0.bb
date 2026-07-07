SUMMARY = "TactiQ Edge residency probe (Phase 2.0, throwaway)"
DESCRIPTION = "Disposable scaffold: runs tactiq-edge-loop once at boot for N \
iterations on a fixed frame (Load/Allocate once, SetInput+Invoke in a loop), \
writes stability + latency to /data/tactiq/edge-loop.txt. Proves the engine \
holds a model resident and serves inference without degradation. NOT a product \
component, NOT the AgriBox cartridge. Remove after the fact is captured."
LICENSE = "CLOSED"

inherit systemd

RDEPENDS:${PN} = "tactiq-edge"

SRC_URI = " \
    file://edge-loop.service \
    file://planthealth_cls_int8.tflite \
    file://frame0.bin \
    file://class_names.txt \
"


do_install() {
    install -d ${D}/usr/share/edge-loop
    install -m 0644 ${UNPACKDIR}/planthealth_cls_int8.tflite ${D}/usr/share/edge-loop/
    install -m 0644 ${UNPACKDIR}/frame0.bin ${D}/usr/share/edge-loop/
    install -m 0644 ${UNPACKDIR}/class_names.txt ${D}/usr/share/edge-loop/
    install -d ${D}${systemd_unitdir}/system
    install -m 0644 ${UNPACKDIR}/edge-loop.service ${D}${systemd_unitdir}/system/
}

SYSTEMD_SERVICE:${PN} = "edge-loop.service"
SYSTEMD_AUTO_ENABLE = "enable"

FILES:${PN} = " \
    /usr/share/edge-loop \
    ${systemd_unitdir}/system/edge-loop.service \
"
