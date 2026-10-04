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
