# shellcheck shell=sh
# /etc/profile.d/tactiq-status.sh: show the device status screen once, at the
# start of an interactive login shell. Non-interactive shells (scp, ssh with a
# command, scripts) are left alone, so nothing is printed into their output.
case $- in
    *i*) [ -x /usr/bin/tactiq-status ] && /usr/bin/tactiq-status ;;
esac
