#!/usr/bin/env bash
#
# check-network-clients.sh: refuse a release image that carries a network
# client removed on purpose.
#
#   check-network-clients.sh <rootfs.manifest>
#
# The production image was found to carry libcurl, libssh and libnl that no
# TactiQ recipe asked for: upstream defaults of rauc and cryptsetup, and the
# single tpm2 binary of tpm2-tools linking libcurl for one tool (#261, #265,
# #268). They were removed, and nothing would notice if a later recipe pulled
# one back in. The manifest is the only place that says what is installed, so
# the release gate reads it.
#
# The list holds what was removed and verified absent, not every possible
# client. Adding a name means first checking the current manifest for it.
#
set -euo pipefail

MANIFEST="${1:?usage: $0 <rootfs.manifest>}"
[[ -r "$MANIFEST" ]] || { echo "::error:: manifest not readable: $MANIFEST" >&2; exit 2; }

FORBIDDEN='^(curl|libcurl[0-9]*|libssh[0-9]*|libnl-.*)$'

hits="$(awk '{print $1}' "$MANIFEST" | grep -E "$FORBIDDEN" || true)"
if [[ -n "$hits" ]]; then
  echo "::error:: release image carries a network client removed on purpose:" >&2
  printf '%s\n' "$hits" | sed 's/^/::error::   /' >&2
  echo "::error:: find what pulls it in: RDEPENDS in tmp/pkgdata/<machine>/runtime/, under the" >&2
  echo "::error:: package name before renaming (libcurl, libssh, libnl-3), not libcurl4 or libssh4" >&2
  exit 1
fi
echo "network clients: none of curl, libcurl, libssh, libnl installed"
