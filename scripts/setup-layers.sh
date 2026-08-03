#!/usr/bin/env bash
#
# Assemble the complete TactiQ OS layer set from public sources at the
# revisions recorded in integration/LAYERS.lock. Companion to
# setup-meta-rauc.sh and modeled on it: the result is deterministic and
# verified — every layer's HEAD must equal its pinned commit, or the
# script fails.
#
# Usage:
#   setup-layers.sh <layers-dir> [layer-name ...]
#
# With no layer names, all layers from LAYERS.lock are set up, plus
# meta-rauc via setup-meta-rauc.sh. With names, only those layers.
#
set -euo pipefail

DEST_ROOT="${1:?usage: $0 <layers-dir> [layer-name ...]}"
shift || true
ONLY=("$@")

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOCK="${SCRIPT_DIR}/../integration/LAYERS.lock"
[ -f "$LOCK" ] || { echo "ERROR: $LOCK not found" >&2; exit 1; }

mkdir -p "$DEST_ROOT"

want() {
  [ ${#ONLY[@]} -eq 0 ] && return 0
  local n; for n in "${ONLY[@]}"; do [ "$n" = "$1" ] && return 0; done
  return 1
}

FAIL=0
while read -r NAME REMOTE COMMIT BRANCH; do
  case "$NAME" in ''|\#*) continue;; esac
  want "$NAME" || continue
  DEST="${DEST_ROOT}/${NAME}"
  if [ -e "$DEST" ]; then
    echo "SKIP  ${NAME}: ${DEST} already exists" >&2
    continue
  fi
  echo ">>> ${NAME} @ ${COMMIT} (${BRANCH})"
  git clone -q --branch "$BRANCH" "$REMOTE" "$DEST" 2>/dev/null \
    || git clone -q "$REMOTE" "$DEST"
  git -C "$DEST" checkout -q "$COMMIT"
  HEAD="$(git -C "$DEST" rev-parse HEAD)"
  if [ "$HEAD" != "$COMMIT" ]; then
    echo "FAIL  ${NAME}: HEAD ${HEAD} != pinned ${COMMIT}" >&2
    FAIL=1
  else
    echo "OK    ${NAME}"
  fi
done < "$LOCK"

# tactiq-os itself is not pinned in the lock: the verifier already has it,
# at the tag they checked out, and that checkout is what must be built. A
# lock line for it could not be written before the commit containing that
# line exists. Place it in the layer set directly instead.
SELF_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
if want tactiq-os; then
  case "$(cd "$DEST_ROOT" && pwd)/" in
    "${SELF_ROOT}"/*)
      echo "FAIL  tactiq-os: <layers-dir> is inside the repository; choose a path outside it" >&2
      FAIL=1;;
    *)
      if [ -e "${DEST_ROOT}/tactiq-os" ]; then
        echo "SKIP  tactiq-os: ${DEST_ROOT}/tactiq-os already exists" >&2
      else
        ln -s "$SELF_ROOT" "${DEST_ROOT}/tactiq-os"
        echo "OK    tactiq-os -> ${SELF_ROOT} (this checkout)"
      fi;;
  esac
fi

# meta-rauc: deterministic reconstruction (pin + patch, tree-hash verified).
# `git am` inside setup-meta-rauc.sh needs a committer identity; on a
# pristine verification host none is configured. The identity does not
# affect the verified tree hash, so a neutral fallback is safe.
if ! git config user.email >/dev/null 2>&1 && [ -z "${GIT_COMMITTER_EMAIL:-}" ]; then
  export GIT_COMMITTER_NAME="layer-setup" GIT_COMMITTER_EMAIL="layer-setup@localhost"
  export GIT_AUTHOR_NAME="layer-setup"    GIT_AUTHOR_EMAIL="layer-setup@localhost"
fi
if want meta-rauc; then
  if [ -e "${DEST_ROOT}/meta-rauc" ]; then
    echo "SKIP  meta-rauc: ${DEST_ROOT}/meta-rauc already exists (remove it to re-verify)" >&2
  elif "${SCRIPT_DIR}/setup-meta-rauc.sh" "$DEST_ROOT"; then
    echo "OK    meta-rauc (via setup-meta-rauc.sh)"
  else
    rm -rf "${DEST_ROOT}/meta-rauc"
    echo "FAIL  meta-rauc: setup-meta-rauc.sh failed; partial directory removed" >&2
    FAIL=1
  fi
fi

[ "$FAIL" -eq 0 ] || { echo "ERROR: one or more layers failed pin verification" >&2; exit 1; }
echo "All requested layers assembled and pin-verified."
