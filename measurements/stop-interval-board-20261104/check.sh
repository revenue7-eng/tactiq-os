#!/bin/sh
# Re-runs the checks of stop-interval-board-20261104.md.
# usage: sh check.sh /path/to/tactiq-stop-verify [keep]
# With "keep", the output of each run is left in verify-*.log.
set -u
V=${1:?usage: sh check.sh /path/to/tactiq-stop-verify [keep]}
KEEP=${2:-}
cd "$(dirname "$0")" || exit 2
DEV=$(cat device_id.txt)
REF=pcr-ref-cnt-20261102.json
fail=0

run() { # name expected-exit expected-text args...
    name=$1; want=$2; text=$3; shift 3
    "$V" "$@" > "verify-$name.log" 2>&1
    rc=$?
    if [ "$rc" -eq "$want" ] && grep -qF -- "$text" "verify-$name.log"; then
        echo "ok   $name"
    else
        echo "FAIL $name (exit $rc)"; fail=1
    fi
    [ "$KEEP" = keep ] || rm -f "verify-$name.log"
}

pair() { # first second
    echo interval "$1.tqsr" "$2.tqsr" --ak ak.pub --device "$DEV" --pcr-ref "$REF" --slot A \
        --nonce-first "$(cat "n${1#r}.txt")" --nonce-second "$(cat "n${2#r}.txt")"
}

run r1 0 'VERDICT     STOPPED' \
    check r1.tqsr --ak ak.pub --device "$DEV" --pcr-ref "$REF" --slot A --nonce "$(cat n1.txt)"

# shellcheck disable=SC2046
run r1-r2 0 'VERDICT     HELD' $(pair r1 r2)
# shellcheck disable=SC2046
run r2-r1 1 'not later' $(pair r2 r1)
# shellcheck disable=SC2046
run r2-r3 1 'moved from 8145 to 8147' $(pair r2 r3)
# shellcheck disable=SC2046
run r3-r4 1 'reset in between (resetCount 380 then 381)' $(pair r3 r4)

if [ "$fail" -eq 0 ]; then echo "ALL CHECKS PASSED"; exit 0; fi
exit 1
