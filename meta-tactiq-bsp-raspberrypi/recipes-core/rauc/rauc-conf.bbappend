# Raspberry Pi 4: its own compatible string, so RAUC on a Pi refuses a Rock
# bundle and the other way round. Same mechanism as the Rock 5T override in
# the common layer's rauc-conf.bbappend; kept in this layer so the common
# file is not touched.
do_install:append:tactiq-rpi4() {
    conf=${D}${sysconfdir}/rauc/system.conf
    sed -i -e 's|^compatible=TactiQ OS Rock5A$|compatible=TactiQ OS RPi4|' "$conf"
    grep -q '^compatible=TactiQ OS RPi4$' "$conf" || \
        bbfatal "RAUC compatible is not set for the Raspberry Pi 4 in $conf"
}
