#!/bin/sh
# Re-runs the three checks of stop-receipt-dev-20261028.md.
# usage: sh check.sh /path/to/tactiq-stop-verify
set -u
V=${1:?usage: sh check.sh /path/to/tactiq-stop-verify}
cd "$(dirname "$0")" || exit 2
DEV=$(cat device_id.txt)
N=$(cat nonce.txt)
fail=0

"$V" check receipt.tqsr --ak ak.pub --device "$DEV" --pcr-ref pcr-ref-op1-20261028.json --slot A --nonce "$N" > out.tmp 2>&1
rc=$?
if [ "$rc" -eq 0 ] && grep -q '^VERDICT     STOPPED$' out.tmp; then echo "ok   stopped, fresh, slot A"; else echo "FAIL main check (exit $rc)"; fail=1; fi

"$V" check receipt.tqsr --ak ak.pub --device "$DEV" --pcr-ref pcr-ref-op1-20261028.json --slot A --nonce "$("$V" nonce)" > out.tmp 2>&1
rc=$?
if [ "$rc" -eq 1 ] && grep -q 'answers another challenge' out.tmp; then echo "ok   refused with a fresh challenge"; else echo "FAIL control: fresh challenge (exit $rc)"; fail=1; fi

"$V" check receipt.tqsr --ak ak.pub --device "$DEV" --pcr-ref pcr-ref-op1-20261028.json --slot B --nonce "$N" > out.tmp 2>&1
rc=$?
if [ "$rc" -eq 1 ] && grep -q "not the reference build's" out.tmp; then echo "ok   refused against slot B"; else echo "FAIL control: slot B (exit $rc)"; fail=1; fi

rm -f out.tmp
if [ "$fail" -eq 0 ]; then echo "ALL CHECKS PASSED"; exit 0; fi
exit 1
