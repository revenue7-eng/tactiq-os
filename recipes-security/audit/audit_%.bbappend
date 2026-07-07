# DEV measurement infrastructure: persistent AVC audit log on /data.
# auditd goes into tactiq-image-dev only (see image recipe), never product.
# Not boot-enabled (ordering cycle: auditd<->data-tactiq-dirs via sysinit);
# started explicitly by edge-probe-run.sh once /data is mounted.

SYSTEMD_AUTO_ENABLE:auditd = "disable"

do_install:append() {
    # Redirect audit log to persistent /data partition (rootfs /var/log is volatile)
    sed -i -e 's|^log_file =.*|log_file = /data/tactiq/audit/audit.log|' \
        ${D}${sysconfdir}/audit/auditd.conf
}
