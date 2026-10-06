# Clock floor at boot: the release date of this tree, not the release date of
# the systemd sources. The board has no RTC, and certificate validity checks
# (RAUC bundle verification among them) need a clock that is not earlier than
# the release the image belongs to.
require recipes-core/tactiq-release/release-derived.inc

PACKAGECONFIG[set-time-epoch] = "-Dtime-epoch=${TACTIQ_TIME_EPOCH},-Dtime-epoch=0"

python () {
    if 'set-time-epoch' not in (d.getVar('PACKAGECONFIG') or '').split():
        bb.fatal("systemd: PACKAGECONFIG lost set-time-epoch; the clock floor would be unset")
}

# /sys/fs/pstore is an API filesystem that PID 1 mounts at startup, but only
# when systemd is built with pstore support. openembedded-core leaves it out
# of the default PACKAGECONFIG, so nothing mounted it and tactiq-log-setup
# found an empty sysfs directory (an SELinux read denial on sysfs_t, first
# seen on the board on 2026-10-06): crash records in ramoops were not
# recovered. The mount stays with PID 1, as tactiq-log-setup.sh requires.
PACKAGECONFIG:append = " pstore"

# The same option builds systemd-pstore.service, which would move the records
# to /var/lib/systemd/pstore, a volatile bind mount on this image, and delete
# them from pstore before tactiq-log-setup copies them to /data. Masked.
do_install:append() {
    install -d ${D}${sysconfdir}/systemd/system
    ln -sf /dev/null ${D}${sysconfdir}/systemd/system/systemd-pstore.service
}
