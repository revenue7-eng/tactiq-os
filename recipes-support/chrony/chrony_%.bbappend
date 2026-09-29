# TactiQ OS: replace the upstream chrony.conf, which points at a public NTP
# pool. Offline-first: the device never contacts public time servers.
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
