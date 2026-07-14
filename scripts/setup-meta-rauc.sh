#!/usr/bin/env bash
#
# Reconstruct the meta-rauc layer used by TactiQ OS builds.
#
# meta-rauc has no wrynose branch upstream; we carry a local patch on top
# of a pinned scarthgap commit. This script makes that reconstruction
# deterministic: the resulting tree hash is identical for anyone who runs it.
#
#   expected tree: ce25181e3275664e5ed66d980ef2e74424861801
#
set -euo pipefail

DEST="${1:?usage: $0 <layers-dir>}/meta-rauc"
PIN="fa18cf1fb2840ba23df0fe79f38ffca4bf7a4816"   # rauc: update to v1.15.2
EXPECTED_TREE="ce25181e3275664e5ed66d980ef2e74424861801"
PATCH="$(cd "$(dirname "$0")/.." && pwd)/integration/meta-rauc-wrynose.patch"

[ -e "$DEST" ] && { echo "ERROR: $DEST exists" >&2; exit 1; }

git clone -q --branch scarthgap https://github.com/rauc/meta-rauc.git "$DEST"
cd "$DEST"
git checkout -q "$PIN"
git am -q "$PATCH"

TREE="$(git rev-parse 'HEAD^{tree}')"
if [ "$TREE" != "$EXPECTED_TREE" ]; then
  echo "FAIL: tree $TREE != expected $EXPECTED_TREE" >&2
  exit 1
fi

echo "meta-rauc OK"
echo "  pin:  $PIN"
echo "  tree: $TREE"
echo "  rauc: $(ls recipes-core/rauc/rauc_*.bb | grep -oP '\d+\.\d+\.\d+')"
