#!/usr/bin/env bash
#
# check-build-input.sh — verify that the build directory builds what the
# tree says it builds.
#
#   check-build-input.sh <layers-dir> <build-dir>
#
# check-layers.sh answers "are the layers the ones recorded in the lock".
# This answers the other half: "is the build assembled from those layers,
# and only from them". The lock verifies the contents of the layer set; it
# does not read bblayers.conf, so it cannot see which layers are actually
# wired in, in what order, or whether a devtool workspace is overriding
# them. Three things are checked, each one already observed to drift:
#
#   1. bblayers.conf is exactly what init-build.sh would generate now from
#      conf/bblayers.conf.in. init-build.sh performs a single ${LAYERS_DIR}
#      substitution and copies the rest literally, so any other difference
#      means the file came from a different template revision or was edited
#      by hand. init-build.sh refuses to overwrite an existing conf, so a
#      stale file is never corrected by re-running it.
#   2. The devtool workspace holds no captured recipe. It sits last in
#      BBLAYERS and overrides every layer above it, including layers the
#      lock has just certified as pinned and clean.
#   3. tactiq-os is identified. It is deliberately absent from LAYERS.lock,
#      for the reason given in check-layers.sh: the repository carrying the
#      lock is identified by the tag the verifier checked out, not by a line
#      inside the file it is reading. That reasoning holds only while the
#      working copy is on a tag; on a local branch there is nothing to
#      identify it by, so the state is reported rather than assumed.
#
# This script is subject to the same exclusion as the lock: it lives in
# tactiq-os and cannot establish its own revision. What it says about the
# repository it ships in is only as good as the tag the reader checked out.
#
# Revision comparison for the agent recipe belongs to tactiq-facts and is
# not repeated here; the SRCREV is printed for the reader, not verified.
#
set -euo pipefail

if [ $# -ne 2 ]; then
  echo "usage: $0 <layers-dir> <build-dir>" >&2
  exit 2
fi

LAYERS_DIR="$(cd "$1" && pwd)"
BUILD_DIR="$(cd "$2" && pwd)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TEMPLATE="${SCRIPT_DIR}/../conf/bblayers.conf.in"
INIT_BUILD="${SCRIPT_DIR}/init-build.sh"
BUILD_CONF="${BUILD_DIR}/conf/bblayers.conf"
WORKSPACE="${BUILD_DIR}/workspace"

FAIL=0
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# --- 1. generated bblayers.conf against the template in this tree ---------

if [ ! -f "$TEMPLATE" ]; then
  echo "FAIL  bblayers: template not found: ${TEMPLATE}" >&2
  FAIL=1
elif [ ! -f "$BUILD_CONF" ]; then
  echo "FAIL  bblayers: ${BUILD_CONF} missing; run init-build.sh" >&2
  FAIL=1
else
  sed "s|\${LAYERS_DIR}|${LAYERS_DIR}|g" "$TEMPLATE" > "${TMP}/expected"
  # The workspace layer is appended by devtool, not by init-build.sh. It is
  # the one permitted deviation; it is checked on its own below.
  grep -vE "^[[:space:]]*${BUILD_DIR}/workspace[[:space:]]*\\\\?[[:space:]]*$" \
    "$BUILD_CONF" > "${TMP}/actual" || true
  if diff -u "${TMP}/expected" "${TMP}/actual" > "${TMP}/diff" 2>&1; then
    echo "OK    bblayers.conf matches conf/bblayers.conf.in in this tree"
  else
    echo "FAIL  bblayers.conf differs from the template it should have come from" >&2
    sed -n '3,$p' "${TMP}/diff" | sed 's/^/        /' >&2
    FAIL=1
  fi
fi

# --- 2. devtool workspace -------------------------------------------------

if [ ! -d "$WORKSPACE" ]; then
  echo "OK    workspace: absent"
else
  CAPTURED=""
  for sub in appends sources; do
    if [ -d "${WORKSPACE}/${sub}" ]; then
      n="$(find "${WORKSPACE}/${sub}" -mindepth 1 -maxdepth 1 | wc -l)"
      [ "$n" -gt 0 ] && CAPTURED="${CAPTURED}${sub}:${n} "
    fi
  done
  if [ -n "$CAPTURED" ]; then
    echo "FAIL  workspace: recipes captured (${CAPTURED% }); the workspace layer" >&2
    echo "        overrides every layer above it, including locked ones" >&2
    find "${WORKSPACE}/appends" -mindepth 1 -maxdepth 1 -printf '        %f\n' \
      2>/dev/null >&2 || true
    FAIL=1
  else
    echo "OK    workspace: no recipe captured"
  fi
  if [ -d "${WORKSPACE}/attic" ] \
     && [ "$(find "${WORKSPACE}/attic" -mindepth 1 -maxdepth 1 | wc -l)" -gt 0 ]; then
    echo "WARN  workspace: attic is not empty; residue from an earlier devtool reset" >&2
  fi
  if [ -f "$BUILD_CONF" ] \
     && grep -qE "^[[:space:]]*${BUILD_DIR}/workspace" "$BUILD_CONF"; then
    echo "WARN  workspace: still wired into BBLAYERS; one devtool modify is enough" >&2
    echo "        to override the locked layers without changing any of them" >&2
  fi
fi

# --- 3. identity of tactiq-os --------------------------------------------

SELF_DIR="${LAYERS_DIR}/tactiq-os"
if [ ! -d "$SELF_DIR" ]; then
  echo "FAIL  tactiq-os: ${SELF_DIR} missing" >&2
  FAIL=1
else
  REAL="$(cd "$SELF_DIR" && pwd -P)"
  [ "$REAL" = "$SELF_DIR" ] || echo "      tactiq-os: ${SELF_DIR} -> ${REAL}"
  if [ ! -e "${REAL}/.git" ]; then
    echo "FAIL  tactiq-os: no git metadata in ${REAL}; revision cannot be" >&2
    echo "        established from the tree" >&2
    FAIL=1
  else
    HEAD="$(git -C "$REAL" rev-parse HEAD)"
    DIRTY="$(git -C "$REAL" status --porcelain 2>/dev/null)"
    if TAG="$(git -C "$REAL" describe --tags --exact-match HEAD 2>/dev/null)"; then
      echo "OK    tactiq-os @ ${TAG} (${HEAD:0:7})"
    else
      BR="$(git -C "$REAL" rev-parse --abbrev-ref HEAD)"
      echo "WARN  tactiq-os: HEAD ${HEAD:0:7} is not a release tag (branch ${BR});" >&2
      echo "        the lock excludes this repository on the assumption that the" >&2
      echo "        verifier identifies it by tag, and there is no tag here" >&2
      if ! git -C "$REAL" rev-parse --abbrev-ref '@{u}' >/dev/null 2>&1; then
        echo "WARN  tactiq-os: no upstream for ${BR}; this revision exists only" >&2
        echo "        on this machine" >&2
      fi
    fi
    if [ -n "$DIRTY" ]; then
      echo "FAIL  tactiq-os: working tree not clean" >&2
      printf '%s\n' "$DIRTY" | sed 's/^/        /' >&2
      FAIL=1
    fi
    RECIPE="$(find "$REAL" -name 'tactiq-agent_*.bb' -print -quit 2>/dev/null || true)"
    if [ -n "$RECIPE" ]; then
      SRCREV="$(sed -n 's/^SRCREV[[:space:]]*=[[:space:]]*"\([0-9a-f]*\)".*/\1/p' \
                  "$RECIPE" | head -1)"
      echo "      agent recipe: $(basename "$RECIPE") SRCREV ${SRCREV:0:7}, comparison owned by tactiq-facts"
    fi
  fi
fi

# --- reported, not checked: init-build.sh preflight vs the template -------

if [ -f "$INIT_BUILD" ] && [ -f "$TEMPLATE" ]; then
  awk '/^BBLAYERS/,/"$/ {
        for (i=1;i<=NF;i++)
          if ($i ~ /LAYERS_DIR/) { sub(/.*LAYERS_DIR}\//,"",$i); split($i,a,"/"); print a[1] }
      }' "$TEMPLATE" | sort -u > "${TMP}/wired"
  sed -n '/REQUIRED_LAYERS=(/,/^)/p' "$INIT_BUILD" \
    | sed '1d;$d' | tr -s ' \t' '\n' | sed '/^$/d' | sort -u > "${TMP}/required"
  MISS="$(comm -23 "${TMP}/wired" "${TMP}/required" | tr '\n' ' ')"
  if [ -n "${MISS// /}" ]; then
    echo "WARN  init-build.sh: REQUIRED_LAYERS does not list ${MISS% }, which the" >&2
    echo "        template wires into BBLAYERS; its preflight check cannot catch a" >&2
    echo "        missing layer that the build then depends on" >&2
  fi
fi

[ "$FAIL" -eq 0 ] || { echo "ERROR: build input does not match the tree" >&2; exit 1; }
echo "Build input matches the tree: bblayers.conf generated from this template, no recipe captured."
