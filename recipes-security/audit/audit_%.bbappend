# auditd in TactiQ OS.
#
# The recipe builds the library (package audit, in both images as an
# RDEPENDS of base packages, tactiq-image.bb) and the daemon with /etc/audit
# (package auditd, installed by neither image). Should auditd ever be
# installed, it is not started at boot (ordering cycle
# auditd <-> data-tactiq-dirs via sysinit).

SYSTEMD_AUTO_ENABLE:auditd = "disable"
