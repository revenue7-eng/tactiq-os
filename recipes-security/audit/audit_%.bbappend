# auditd in TactiQ OS.
#
# audit is in the production image as well: it is an RDEPENDS of dbus-1,
# shadow-base, libsemanage2 and policycoreutils-setfiles (tactiq-image.bb).
# This append therefore applies to both profiles and holds only what is
# right for both: auditd is not started at boot (ordering cycle
# auditd <-> data-tactiq-dirs via sysinit).
#
# The development image points log_file at the persistent measurement tree
# on /data; that is done in tactiq-image-dev.bb on the image, not here, so
# the production auditd.conf keeps the upstream log_file. scripts/mk-release.sh
# refuses a release whose auditd.conf names the measurement tree
# (check-release-no-dev.py).

SYSTEMD_AUTO_ENABLE:auditd = "disable"
