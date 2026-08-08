#!/usr/bin/env bash
#
# Verify, or record, the state of the assembled layer set.
#
#   check-layers.sh --check <layers-dir>   verify the tree against LAYERS.lock
#   check-layers.sh --emit  <layers-dir>   print the lock body for that tree
#
# --check is the release gate. setup-layers.sh verifies a layer's HEAD at
# the moment it checks it out, which cannot detect anything that happens
# afterwards. This checks the tree as it is at build time: every layer at
# its pinned commit AND with a clean working tree. The lock for v2.1.0-rc6
# had to record that a clean tree was "asserted, not proven"; this proves
# it, or fails.
#
# tactiq-os is deliberately not covered: the repository carrying the lock
# is identified by the tag the verifier checked out, not by a line inside
# the file it is reading. meta-rauc is not in the lock either; it is
# verified by tree hash, the value being read from setup-meta-rauc.sh so
# the constant lives in exactly one place.
#
set -euo pipefail

MODE="${1:?usage: $0 --check|--emit <layers-dir>}"
DEST_ROOT="${2:?usage: $0 --check|--emit <layers-dir>}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOCK="${SCRIPT_DIR}/../integration/LAYERS.lock"
SETUP_RAUC="${SCRIPT_DIR}/setup-meta-rauc.sh"

SELF="tactiq-os"

emit_layer() {   # <dir>
  local d="$1" name remote commit branch
  name="$(basename "$d")"
  [ "$name" = "$SELF" ] && return 0
  [ "$name" = "meta-rauc" ] && return 0
  git -C "$d" rev-parse --git-dir >/dev/null 2>&1 || return 0
  remote="$(git -C "$d" remote get-url origin 2>/dev/null || echo UNKNOWN)"
  commit="$(git -C "$d" rev-parse HEAD)"
  branch="$(git -C "$d" for-each-ref --points-at=HEAD --format='%(refname:short)' \
              'refs/remotes/origin/*' 2>/dev/null | head -1 | sed 's|^origin/||')"
  [ -n "$branch" ] || branch="$(git -C "$d" rev-parse --abbrev-ref HEAD)"
  printf '%s\t%s\t%s\t%s\n' "$name" "$remote" "$commit" "$branch"
}

if [ "$MODE" = "--emit" ]; then
  for d in "$DEST_ROOT"/*/; do emit_layer "${d%/}"; done | sort | awk -F'\t' '
    { for (i=1;i<=NF;i++) { c[NR,i]=$i; if (length($i)>w[i]) w[i]=length($i) } n=NR }
    END { for (r=1;r<=n;r++) printf "%-*s  %-*s  %s  %s\n",
            w[1], c[r,1], w[2], c[r,2], c[r,3], c[r,4] }'
  exit 0
fi

[ "$MODE" = "--check" ] || { echo "ERROR: unknown mode $MODE" >&2; exit 2; }
[ -f "$LOCK" ] || { echo "ERROR: $LOCK not found" >&2; exit 1; }

FAIL=0
SEEN=0
# LAYERS.lock columns: <layer> <remote> <commit> <upstream-branch>; remote and
# branch are recorded for the reader and for --emit, not used by --check.
while read -r NAME _ COMMIT _; do
  case "$NAME" in ''|\#*) continue;; esac
  if [ "$NAME" = "$SELF" ]; then
    echo "FAIL  ${NAME}: lock must not pin the repository that carries it" >&2
    FAIL=1; continue
  fi
  SEEN=$((SEEN+1))
  DEST="${DEST_ROOT}/${NAME}"
  if [ ! -d "$DEST" ]; then
    echo "FAIL  ${NAME}: ${DEST} missing" >&2; FAIL=1; continue
  fi
  if [ ! -e "${DEST}/.git" ]; then
    echo "FAIL  ${NAME}: no git metadata in ${DEST}; the layer was copied, not" >&2
    echo "        cloned, so its revision cannot be established from the tree" >&2
    FAIL=1; continue
  fi
  if ! HEAD="$(git -C "$DEST" rev-parse HEAD 2>&1)"; then
    echo "FAIL  ${NAME}: git: ${HEAD}" >&2; FAIL=1; continue
  fi
  if [ "$HEAD" != "$COMMIT" ]; then
    echo "FAIL  ${NAME}: HEAD ${HEAD} != locked ${COMMIT}" >&2; FAIL=1; continue
  fi
  DIRTY="$(git -C "$DEST" status --porcelain 2>/dev/null)"
  if [ -n "$DIRTY" ]; then
    echo "FAIL  ${NAME}: working tree not clean" >&2
    printf '%s\n' "$DIRTY" | sed 's/^/        /' >&2
    FAIL=1; continue
  fi
  echo "OK    ${NAME} @ ${COMMIT}"
done < "$LOCK"

if [ -d "${DEST_ROOT}/meta-rauc" ]; then
  EXPECTED="$(grep -oE 'EXPECTED_TREE="[0-9a-f]{40}"' "$SETUP_RAUC" | head -1 | cut -d'"' -f2)"
  TREE="$(git -C "${DEST_ROOT}/meta-rauc" rev-parse 'HEAD^{tree}' 2>/dev/null || echo none)"
  DIRTY="$(git -C "${DEST_ROOT}/meta-rauc" status --porcelain 2>/dev/null)"
  if [ -z "$EXPECTED" ]; then
    echo "FAIL  meta-rauc: no EXPECTED_TREE in $(basename "$SETUP_RAUC")" >&2; FAIL=1
  elif [ "$TREE" != "$EXPECTED" ]; then
    echo "FAIL  meta-rauc: tree ${TREE} != expected ${EXPECTED}" >&2; FAIL=1
  elif [ -n "$DIRTY" ]; then
    echo "FAIL  meta-rauc: working tree not clean" >&2; FAIL=1
  else
    echo "OK    meta-rauc @ tree ${TREE}"
  fi
else
  echo "FAIL  meta-rauc: ${DEST_ROOT}/meta-rauc missing" >&2; FAIL=1
fi

# A directory present in the layer set but absent from the lock is an
# unrecorded build input if bblayers.conf references it. Reported, not
# fatal: presence alone does not mean the build used it.
for d in "$DEST_ROOT"/*/; do
  n="$(basename "${d%/}")"
  case "$n" in "$SELF"|meta-rauc) continue;; esac
  grep -qE "^[[:space:]]*${n}[[:space:]]" "$LOCK" \
    || echo "WARN  ${n}: present in the layer set, absent from the lock" >&2
done

[ "$SEEN" -gt 0 ] || { echo "ERROR: lock contained no layers" >&2; exit 1; }
[ "$FAIL" -eq 0 ] || { echo "ERROR: layer set does not match LAYERS.lock" >&2; exit 1; }
echo "Layer set matches LAYERS.lock: ${SEEN} layers pinned and clean, meta-rauc tree verified."
