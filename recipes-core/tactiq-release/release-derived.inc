# Values derived from release-rev.inc for recipes that need the release
# identity in another form. Nothing here is set by hand; change
# release-rev.inc instead.
require recipes-core/tactiq-release/release-rev.inc

def tactiq_rauc_version(d):
    import re
    rev = d.getVar('TACTIQ_OS_RELEASE_REV') or ''
    m = re.match(r'^v(\d+\.\d+\.\d+)(?:-rc(\d+))?$', rev)
    if not m:
        bb.fatal("TACTIQ_OS_RELEASE_REV '%s' is neither vX.Y.Z nor vX.Y.Z-rcN" % rev)
    return m.group(1) + ('-rc.%s' % m.group(2) if m.group(2) else '')

def tactiq_time_epoch(d):
    import calendar, time
    date = d.getVar('TACTIQ_OS_RELEASE_DATE') or ''
    try:
        return str(calendar.timegm(time.strptime(date, '%Y-%m-%d')))
    except ValueError:
        bb.fatal("TACTIQ_OS_RELEASE_DATE '%s' is not YYYY-MM-DD" % date)

# RAUC bundle version and the device's min-bundle-version. "rc.N", not "rcN":
# semantic versioning compares a numeric identifier as a number, so rc.14
# orders after rc.9, and a final X.Y.Z orders after every X.Y.Z-rc.N.
TACTIQ_RAUC_VERSION = "${@tactiq_rauc_version(d)}"

# Floor for the system clock at boot (systemd time-epoch): midnight UTC of the
# release date.
TACTIQ_TIME_EPOCH = "${@tactiq_time_epoch(d)}"
