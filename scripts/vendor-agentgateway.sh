#!/usr/bin/env bash
#
# Regenerate the agentgateway vendored crate tree.
#
#   scripts/vendor-agentgateway.sh <dl-dir> [--pack]
#
# Why this exists
# ---------------
# agentgateway pulls three crates from git forks, not from crates.io:
# http-serde, schemars and wiremock-rs. The cargo-update-recipe-crates class
# only emits crate:// entries for packages whose Cargo.lock source contains
# "crates.io", so those three cannot be expressed that way and the recipe
# builds from a vendored tree instead.
#
# Until now that tree was produced by hand and lived only in one machine's
# DL_DIR: a clean checkout could not build agentgateway at all, and nothing
# recorded what the directory was supposed to contain. This script closes both
# gaps. `cargo vendor --locked` against a pinned SRCREV is byte-for-byte
# reproducible -- verified here by generating the tree twice, the second time
# with the local cargo registry cache removed, and comparing with diff -r: zero
# differences across 727 crates. So the tree does not need to be archived to be
# trustworthy, it needs to be *regenerable* and *checkable*, which is what the
# recorded hash below provides.
#
# With --pack the script also writes a deterministic tarball, for a premirror
# or a release asset. That is a speed optimisation, not a correctness one: the
# hash is the same whether the tree was fetched or rebuilt locally.
#
# Note on tar: naive `tar -czf` is NOT deterministic here -- two runs over
# identical trees produced different archives, because readdir order and mtimes
# leak in. The invocation below sorts the member list, zeroes ownership and
# timestamps, pins the format and drops the gzip header timestamp.
#
set -euo pipefail

REPO="https://github.com/agentgateway/agentgateway.git"
# Must match SRCREV in recipes-connectivity/agentgateway/agentgateway_1.1.0.bb.
SRCREV="d204f9ce1ac785d4b23145cce64c4a34a5c540c9"
PV="1.1.0"

# sha256 of the deterministic tarball produced from this SRCREV.
# Regenerate with --pack and update both this value and the recipe if SRCREV
# ever moves; they are two halves of one fact and must not drift apart.
EXPECTED_SHA256="7f40a2e7baf8bc9d606212bca5e6ac0e7202fca78f6eaaaff1672d6d20c53066"

DL_DIR="${1:-}"
PACK="${2:-}"
[ -n "$DL_DIR" ] || { echo "usage: $0 <dl-dir> [--pack]" >&2; exit 2; }

command -v cargo >/dev/null || { echo "FAIL: cargo not on PATH" >&2; exit 1; }

DEST="${DL_DIR%/}/agentgateway-vendor-${PV}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

if [ -d "$DEST" ]; then
  echo "SKIP  $DEST already exists"
  echo "      remove it first if you want to regenerate"
  exit 0
fi

echo ">>> cloning agentgateway @ ${SRCREV:0:12}"
git init -q "$WORK/src"
git -C "$WORK/src" remote add origin "$REPO"
git -C "$WORK/src" fetch -q --depth 1 origin "$SRCREV"
git -C "$WORK/src" checkout -q "$SRCREV"

# --locked is the whole point: vendoring resolves from the committed Cargo.lock
# rather than re-solving the dependency graph, which is what makes the output a
# function of SRCREV alone.
echo ">>> cargo vendor --locked (727 crates, a few minutes)"
( cd "$WORK/src" && cargo vendor --locked "$WORK/vendor" >/dev/null )

echo ">>> hashing"
ACTUAL="$( cd "$WORK/vendor" && find . -print0 | LC_ALL=C sort -z \
  | tar --owner=0 --group=0 --numeric-owner --mtime=@0 --format=gnu \
        --no-recursion --null -T - -cf - \
  | gzip -n | sha256sum | cut -d' ' -f1 )"

if [ "$ACTUAL" != "$EXPECTED_SHA256" ]; then
  echo "FAIL  vendored tree does not match the recorded hash" >&2
  echo "      expected $EXPECTED_SHA256" >&2
  echo "      actual   $ACTUAL" >&2
  echo "      Either SRCREV moved without this script being updated, or a" >&2
  echo "      dependency source changed under a tag. Do not paper over this." >&2
  exit 1
fi
echo "OK    matches recorded hash ${ACTUAL:0:16}..."

mkdir -p "$DL_DIR"
mv "$WORK/vendor" "$DEST"
echo "OK    $DEST"

if [ "$PACK" = "--pack" ]; then
  OUT="${DL_DIR%/}/agentgateway-vendor-${PV}.tar.gz"
  ( cd "$DEST" && find . -print0 | LC_ALL=C sort -z \
    | tar --owner=0 --group=0 --numeric-owner --mtime=@0 --format=gnu \
          --no-recursion --null -T - -cf - ) | gzip -n > "$OUT"
  echo "OK    $OUT"
  sha256sum "$OUT"
fi
