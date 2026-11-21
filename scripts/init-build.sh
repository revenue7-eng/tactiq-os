#!/usr/bin/env bash
#
# init-build.sh — materialize a bitbake BUILDDIR for a TactiQ OS release
# by expanding conf/bblayers.conf.in and conf/local.conf.in with
# absolute paths to the layer set assembled by scripts/setup-layers.sh.
#
# Usage:
#   init-build.sh <layers-dir> <build-dir> [target]
#
# target selects the template pair and the layers checked for:
#   rock5a (default)  conf/bblayers.conf.in,      conf/local.conf.in
#   rpi4              conf/bblayers-rpi4.conf.in, conf/local-rpi4.conf.in
#
# The layers-dir must contain the layer set that scripts/setup-layers.sh
# produces; the script verifies this before writing anything.
#
# After successful completion:
#   source <layers-dir>/openembedded-core/oe-init-build-env <build-dir>
#   bitbake tactiq-image
#
set -euo pipefail

if [ $# -lt 2 ] || [ $# -gt 3 ]; then
  echo "usage: $0 <layers-dir> <build-dir> [rock5a|rpi4]" >&2
  exit 2
fi

LAYERS_DIR="$(cd "$1" && pwd)"
BUILD_DIR="$2"
TARGET="${3:-rock5a}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TEMPLATE_DIR="${SCRIPT_DIR}/../conf"

# Required layer directories per target, as listed in the target's
# bblayers template. scripts/check-build-input.sh reads these arrays by name.
REQUIRED_LAYERS_rock5a=(
  openembedded-core meta-openembedded meta-selinux meta-arm
  meta-rockchip meta-rauc meta-tensorflow-lite meta-security
  tactiq-os tactiq-os-selinux bitbake
)
REQUIRED_LAYERS_rpi4=(
  openembedded-core meta-openembedded meta-selinux
  meta-raspberrypi meta-rauc meta-security
  tactiq-os tactiq-os-selinux bitbake
)

case "$TARGET" in
  rock5a)
    BBLAYERS_T="bblayers.conf.in"; LOCAL_T="local.conf.in"
    REQUIRED_LAYERS=("${REQUIRED_LAYERS_rock5a[@]}");;
  rpi4)
    BBLAYERS_T="bblayers-rpi4.conf.in"; LOCAL_T="local-rpi4.conf.in"
    REQUIRED_LAYERS=("${REQUIRED_LAYERS_rpi4[@]}");;
  *)
    echo "ERROR: unknown target '${TARGET}' (known: rock5a, rpi4)" >&2
    exit 2;;
esac

MISSING=()
for L in "${REQUIRED_LAYERS[@]}"; do
  [ -d "${LAYERS_DIR}/${L}" ] || MISSING+=("${L}")
done
if [ ${#MISSING[@]} -ne 0 ]; then
  echo "ERROR: missing layers in ${LAYERS_DIR}:" >&2
  printf '  - %s\n' "${MISSING[@]}" >&2
  echo "Run scripts/setup-layers.sh ${LAYERS_DIR} first." >&2
  exit 1
fi

for T in "$BBLAYERS_T" "$LOCAL_T"; do
  [ -f "${TEMPLATE_DIR}/${T}" ] || { echo "ERROR: template not found: ${TEMPLATE_DIR}/${T}" >&2; exit 1; }
done

mkdir -p "${BUILD_DIR}/conf"
BUILD_CONF="${BUILD_DIR}/conf"

# Refuse to overwrite existing conf files silently.
for C in bblayers.conf local.conf; do
  if [ -e "${BUILD_CONF}/${C}" ]; then
    echo "ERROR: ${BUILD_CONF}/${C} already exists; remove it or choose a different <build-dir>" >&2
    exit 1
  fi
done

# Placeholder substitution. Only ${LAYERS_DIR} is expanded; every other
# ${...} in the templates is bitbake syntax and must be preserved literally.
sed "s|\${LAYERS_DIR}|${LAYERS_DIR}|g" \
    "${TEMPLATE_DIR}/${BBLAYERS_T}" > "${BUILD_CONF}/bblayers.conf"
cp "${TEMPLATE_DIR}/${LOCAL_T}" "${BUILD_CONF}/local.conf"

# Sanity check: the resulting bblayers.conf must contain no unresolved
# placeholders and every listed BBLAYERS entry must exist on disk.
if grep -q '\${LAYERS_DIR}' "${BUILD_CONF}/bblayers.conf"; then
  echo "ERROR: unresolved \${LAYERS_DIR} in generated bblayers.conf" >&2
  exit 1
fi
awk '
  /^BBLAYERS/,/"$/ { for (i=1;i<=NF;i++) if ($i ~ /^\//) print $i }
' "${BUILD_CONF}/bblayers.conf" | while read -r P; do
  [ -d "$P" ] || { echo "ERROR: BBLAYERS entry not a directory: $P" >&2; exit 1; }
done

echo "OK. Wrote (target ${TARGET}):"
echo "  ${BUILD_CONF}/bblayers.conf"
echo "  ${BUILD_CONF}/local.conf"
echo
echo "Next:"
echo "  source ${LAYERS_DIR}/openembedded-core/oe-init-build-env ${BUILD_DIR}"
echo "  bitbake tactiq-image"
