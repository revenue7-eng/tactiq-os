# auditd in TactiQ OS.
#
# The recipe builds the library (package audit, an RDEPENDS of base
# packages in both images) and the daemon with /etc/audit (package auditd,
# installed by tactiq-image.bb and so by both images).
#
# The log persists across reboot the way the journal does: /data/log/audit
# is created by tactiq-log-setup before sysinit and bound onto
# /var/log/audit (var-volatile-log-audit.mount, tactiq-config). auditd keeps
# its upstream log_file, and its upstream rotation (max_log_file 8 MB,
# num_logs 5) bounds the space on /data.
#
# An earlier note said auditd could not start at boot because of an
# ordering cycle with data-tactiq-dirs through sysinit. That cycle exists
# only if auditd waits for data-tactiq-dirs, which runs after sysinit.
# Nothing here does: the bind depends on tactiq-log-setup, which runs
# before sysinit, as auditd itself does.

FILESEXTRAPATHS:prepend:tactiq := "${THISDIR}/files:"

SRC_URI:append:tactiq = " \
    file://30-tactiq.rules \
    file://tactiq-data.rules \
    file://tactiq-audit-data-rules.service \
    file://auditd.service.d/10-tactiq-log.conf \
    file://audit-rules.service.d/10-tactiq-load.conf \
"

SYSTEMD_SERVICE:auditd += "tactiq-audit-data-rules.service"
SYSTEMD_AUTO_ENABLE:auditd = "enable"

do_install:append:tactiq() {
    # The rules: upstream base configuration, then ours, in the order
    # augenrules would join them. Assembled here because the rootfs is
    # read-only and augenrules cannot write audit.rules on the device.
    install -m 0640 ${UNPACKDIR}/30-tactiq.rules ${D}${sysconfdir}/audit/rules.d/30-tactiq.rules
    cat ${S}/rules/10-base-config.rules ${UNPACKDIR}/30-tactiq.rules > ${D}${sysconfdir}/audit/audit.rules
    chmod 0640 ${D}${sysconfdir}/audit/audit.rules

    auditctl=${base_sbindir}/auditctl
    [ -x ${D}${auditctl} ] || bbfatal "audit: ${auditctl} not installed, the rules drop-in would name a missing binary"

    # Watches on /data, loaded once data-tactiq-dirs has made the
    # directories (see tactiq-data.rules).
    install -m 0640 ${UNPACKDIR}/tactiq-data.rules ${D}${sysconfdir}/audit/tactiq-data.rules
    sed -e "s|@AUDITCTL@|${auditctl}|" ${UNPACKDIR}/tactiq-audit-data-rules.service \
        > ${D}${systemd_system_unitdir}/tactiq-audit-data-rules.service
    grep -q "^ExecStart=${auditctl} -R " ${D}${systemd_system_unitdir}/tactiq-audit-data-rules.service \
        || bbfatal "audit: data rules unit was not filled in"

    install -d ${D}${systemd_system_unitdir}/auditd.service.d
    install -m 0644 ${UNPACKDIR}/auditd.service.d/10-tactiq-log.conf ${D}${systemd_system_unitdir}/auditd.service.d/10-tactiq-log.conf
    install -d ${D}${systemd_system_unitdir}/audit-rules.service.d
    sed -e "s|@AUDITCTL@|${auditctl}|" ${UNPACKDIR}/audit-rules.service.d/10-tactiq-load.conf \
        > ${D}${systemd_system_unitdir}/audit-rules.service.d/10-tactiq-load.conf
    grep -q "^ExecStart=${auditctl} -R " ${D}${systemd_system_unitdir}/audit-rules.service.d/10-tactiq-load.conf \
        || bbfatal "audit: rules drop-in was not filled in"
}

FILES:auditd:append:tactiq = " \
    ${systemd_system_unitdir}/tactiq-audit-data-rules.service \
    ${systemd_system_unitdir}/auditd.service.d \
    ${systemd_system_unitdir}/audit-rules.service.d \
"
