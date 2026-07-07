SUMMARY = "TactiQ Edge Phase 2 daemon+probe measurement (throwaway)"
DESCRIPTION = "Disposable scaffold: at boot brings up tactiq-edge-daemon on a \
unix socket, runs tactiq-edge-probe against it for N iterations on a fixed \
frame, writes round-trip latency + class stability to /data/tactiq/edge-probe.txt. \
Proves the resident daemon serves inference over the wire (protocol v0). NOT a \
product component. Remove after the round-trip fact is captured."
LICENSE = "CLOSED"

inherit systemd

RDEPENDS:${PN} = "tactiq-edge"

SRC_URI = " \
    file://edge-probe.service \
    file://edge-probe-run.sh \
    file://planthealth_cls_int8.tflite \
    file://frame0.bin \
    file://class_names.txt \
"

do_install() {
    install -d ${D}/usr/share/edge-probe
    install -m 0644 ${UNPACKDIR}/planthealth_cls_int8.tflite ${D}/usr/share/edge-probe/
    install -m 0644 ${UNPACKDIR}/frame0.bin ${D}/usr/share/edge-probe/
    install -m 0644 ${UNPACKDIR}/class_names.txt ${D}/usr/share/edge-probe/
    install -d ${D}/usr/bin
    install -m 0755 ${UNPACKDIR}/edge-probe-run.sh ${D}/usr/bin/
    install -d ${D}${systemd_unitdir}/system
    install -m 0644 ${UNPACKDIR}/edge-probe.service ${D}${systemd_unitdir}/system/
}

SYSTEMD_SERVICE:${PN} = "edge-probe.service"
SYSTEMD_AUTO_ENABLE = "enable"

FILES:${PN} = " \
    /usr/share/edge-probe \
    /usr/bin/edge-probe-run.sh \
    ${systemd_unitdir}/system/edge-probe.service \
"
