#!/usr/bin/env bash
# Negative test: the files the runtime on the board can read cannot produce a
# signature with the bound key on another TPM.
#
# Run from this directory on a host with swtpm and tpm2-tools:
#     bash negative.sh > negative-swtpm.log 2>&1
# It starts a fresh software TPM (swtpm) in a temporary directory, copies the
# board's key files into a scratch directory and tries three ways to use them.
# Each attempt is expected to fail; the control step (a primary created on the
# software TPM itself) is expected to succeed. Nothing in this directory is
# changed except the log you redirect to.
set -u
here=$(cd "$(dirname "$0")" && pwd)
work=$(mktemp -d)
state=$(mktemp -d)
port=$((20000 + RANDOM % 20000))
trap 'kill "$(cat "$state/pid" 2>/dev/null)" 2>/dev/null; rm -rf "$work" "$state"' EXIT

echo "host: $(uname -srm)"
echo "swtpm: $(swtpm --version 2>&1 | head -n 1)"
echo "tpm2-tools: $(tpm2_load -v 2>&1 | head -n 1)"
for f in bind.pub bind.priv bind.ctx primary.ctx pop.digest; do
  cp "$here/$f" "$work/"
  echo "input $(sha256sum "$here/$f" | cut -d' ' -f1)  $f"
done

swtpm socket --tpm2 --tpmstate dir="$state" \
  --server type=tcp,port="$port" --ctrl type=tcp,port=$((port + 1)) \
  --flags not-need-init,startup-clear --daemon --pid file="$state/pid" || exit 2
sleep 1
export TPM2TOOLS_TCTI="swtpm:host=127.0.0.1,port=$port"
cd "$work"

fail=0
expect_fail() {
  local label=$1; shift
  echo "== $label"
  echo "\$ $*"
  if "$@"; then echo "UNEXPECTED: succeeded"; fail=1; else echo "refused as expected (rc=$?)"; fi
}

echo "== control: a primary created by this TPM from the same template"
echo "\$ tpm2_createprimary -C o -g sha256 -G ecc256 -c other-primary.ctx"
if tpm2_createprimary -C o -g sha256 -G ecc256 -c other-primary.ctx > /dev/null; then
  echo "succeeded as expected"
else
  echo "UNEXPECTED: control failed, the refusals below say nothing"; exit 2
fi

expect_fail "A: load the board's key blob under this TPM's primary" \
  tpm2_load -C other-primary.ctx -u bind.pub -r bind.priv -c a.ctx
expect_fail "B1: sign with the board's saved key context" \
  tpm2_sign -c bind.ctx -g sha256 -d -o b1.sig pop.digest
expect_fail "B2: load the key blob under the board's saved primary context" \
  tpm2_load -C primary.ctx -u bind.pub -r bind.priv -c b2.ctx

ls ./*.sig > /dev/null 2>&1 && { echo "UNEXPECTED: a signature file exists"; fail=1; }
echo "RESULT: $([ $fail -eq 0 ] && echo 'no signature produced on the other TPM' || echo 'FAILED')"
exit $fail
