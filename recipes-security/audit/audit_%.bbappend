# DEV measurement infrastructure: persistent AVC audit log on /data.
# auditd goes into tactiq-image-dev only (see image recipe), never product.
# That separation is enforced by the image IMAGE_INSTALL, not by this file:
# a bbappend applies to the recipe wherever it is parsed, so if auditd ever
# enters the product image it arrives with log_file pointing at the
# measurement tree. Gate log_file on the image at that point.
# Not boot-enabled (ordering cycle: auditd<->data-tactiq-dirs via sysinit);
# started explicitly by edge-probe-run.sh once /data is mounted.

SYSTEMD_AUTO_ENABLE:auditd = "disable"

do_install:append() {
    # Redirect audit log to persistent /data partition (rootfs /var/log is volatile)
    sed -i -e 's|^log_file =.*|log_file = /data/tactiq/measurement/audit/audit.log|' \
        ${D}${sysconfdir}/audit/auditd.conf
}
