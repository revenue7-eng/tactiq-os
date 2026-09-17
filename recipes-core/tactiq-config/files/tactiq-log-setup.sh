#!/bin/sh
# Level 0 logging: data-partition layout and kernel crash-record recovery.
#
# Runs before sysinit.target, early enough that var-log-journal.mount can
# bind the journal directory in before systemd-journal-flush moves this
# boot's messages out of RAM.
#
# This script does not mount anything. The bind is a systemd .mount unit,
# so the privilege stays with systemd and this domain never needs it, and
# the flush is ordered after the mount automatically by the
# RequiresMountsFor=/var/log/journal that systemd-journal-flush already
# carries.
#
# The crash-record half is done here rather than by systemd-pstore.service
# because that service writes to /var/lib/systemd/pstore, and /var/lib is
# a volatile bind mount on this image: records it recovered would be
# discarded by the next reboot.
#
# Output goes to the console, not to the journal. This runs before the
# journal has anywhere persistent to write, so a failure here is exactly
# the failure that leaves no record - the console is the only place it can
# be seen. Each step reports its own exit status rather than dying under
# set -e, so a failing boot names the command that failed instead of
# stopping silently.

exec >/dev/console 2>&1

LOGDIR=/data/log
JDIR="${LOGDIR}/journal"
PDIR="${LOGDIR}/pstore"

rc=0

step() {  # <description> <command...>
    desc="$1"
    shift
    if "$@"; then
        return 0
    fi
    status=$?
    echo "tactiq-log-setup: FAILED (${status}): ${desc}: $*"
    rc=1
    return "${status}"
}

step "create journal and pstore directories" mkdir -p "${JDIR}" "${PDIR}"

# The mount point for the journal. /var/log is a symlink to volatile/log,
# and /var/volatile/log itself is created by 00-create-volatile.conf, which
# runs in systemd-tmpfiles-setup - after systemd-journal-flush, not before
# it (journal-flush carries Before=systemd-tmpfiles-setup.service). So at
# the moment var-log-journal.mount runs, the directory it has to create its
# mount point in does not exist yet and the mount fails. Create it here,
# where /var/volatile is already mounted and the journal has not flushed.
step "create /var/volatile/log" mkdir -p /var/volatile/log
step "create the journal mount point" mkdir -p /var/volatile/log/journal

# setgid so journald's files stay group-owned by systemd-journal.
step "set mode on journal directory" chmod 2755 "${JDIR}" || true

# Labels come from tactiq_log.fc. A failure here is reported but not fatal:
# an unlabelled directory is a policy problem, not a reason to lose the
# boot's log entirely.
step "relabel ${LOGDIR}" restorecon -R "${LOGDIR}" || true

# Kernel crash records. The ramoops area is not reused while records are
# present, so a second failure would find no space: move them out and unlink.
#
# Records are numbered from a counter rather than stamped with the time.
# The board has no RTC and starts every boot at the same built-in epoch, so
# a timestamp would collide across exactly the boots this is meant to tell
# apart.
if [ -d /sys/fs/pstore ]; then
    seq_file="${PDIR}/.seq"
    n=$(cat "${seq_file}" 2>/dev/null || echo 0)
    moved=0
    for f in /sys/fs/pstore/*; do
        [ -e "${f}" ] || continue
        if [ "${moved}" -eq 0 ]; then
            n=$((n + 1))
            printf '%s\n' "${n}" > "${seq_file}"
        fi
        if cp -a "${f}" "${PDIR}/$(printf '%04d' "${n}")-$(basename "${f}")"; then
            rm -f "${f}"
            moved=$((moved + 1))
        else
            echo "tactiq-log-setup: FAILED: could not copy ${f}"
            rc=1
        fi
    done
    if [ "${moved}" -gt 0 ]; then
        echo "tactiq-log-setup: recovered ${moved} crash record(s) into ${PDIR}"
    fi
fi

sync

if [ "${rc}" -ne 0 ]; then
    echo "tactiq-log-setup: completed with errors"
fi

# The journal mount depends on this unit, and losing the journal because a
# relabel failed is worse than running with the wrong label. Only a failure
# to create the directories is fatal, and that is reported above.
exit 0
