#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
#
# mk-repro-report.py — generate a per-file reproducibility report from two
# independent builds of the same tag.
#
# Why this exists
# ---------------
# The v2.1.0-rc6 cycle produced a reproducibility report whose summary
# disagreed with the release notes and SUPPLY_CHAIN.md that cited it (one
# said "10 files differ, NOT achieved", the others "4 differ, verified"),
# and the file-hash-diff.txt it pointed at was never committed. Both builds
# quoted in both write-ups were the same two builds, so this was a recording
# drift, not a measurement disagreement: the report had been produced by an
# ad-hoc script that was not in the tree and therefore could not be re-run.
#
# This script is that generator, committed.
#
# History policy (deliberate, do not "fix")
# -----------------------------------------
# This tool NEVER modifies or deletes an existing file. If an output path
# already exists it aborts. Superseded reports stay in the tree with their
# original numbers and their original date; a later measurement is a NEW
# dated report placed beside the old one. The audit trail is the product —
# a report that was wrong on 2026-07-21 is evidence of what was believed on
# 2026-07-21 and is not ours to retouch.
#
# Usage
#   mk-repro-report.py --sbom-a A.spdx.json --sbom-b B.spdx.json \
#       --release v2.1.0-rc7 --distro wrynose [--build-id-a ...] \
#       [--artifact-a name=sha256 ...] [--outdir docs/reproducibility]
#
# Exit codes
#   0  report written (regardless of whether reproducibility was achieved)
#   1  usage / input error
#   2  refused to overwrite an existing output file

import argparse
import datetime
import json
import os
import sys
from collections import OrderedDict

# Artifacts that are expected to differ between two builds even when every
# byte of rootfs *content* is identical: filesystem images embed their own
# creation-time metadata (superblock UUID/timestamps) and the .wic wrappers
# inherit it. Divergence here is not a content difference. Anything NOT in
# this list that differs is a genuine finding and is reported as such.
IMAGE_LEVEL_SUFFIXES = (
    ".ext4",
    ".wic",
    ".wic.bmap",
    ".wic.gz",
    ".wic.zst",
    ".hddimg",
    ".iso",
)

# Files known to be generated per-build inside the rootfs. These ARE content
# differences and are reported, but flagged with their known cause so the
# reader is not left guessing. Keep this list short and justified.
KNOWN_VOLATILE = {
    "/etc/machine-id": "generated at first boot / rootfs assembly",
    "/var/lib/systemd/random-seed": "entropy seed, regenerated per build",
    "/etc/ssh/ssh_host_": "host keys, regenerated per build",
}


def die(msg, code=1):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def load_file_hashes(path):
    """Extract {filename: sha256} from an SPDX 2.x or 3.x document.

    Returns (mapping, spdx_flavour). Filenames are normalised to a leading
    '/' so the two SPDX generations compare cleanly.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        die(f"cannot read SBOM {path}: {exc}")

    out = {}

    # --- SPDX 3.x (Yocto wrynose and later): JSON-LD graph ---------------
    graph = doc.get("@graph")
    if isinstance(graph, list):
        for el in graph:
            if not isinstance(el, dict):
                continue
            if el.get("type") != "software_File":
                continue
            name = el.get("name")
            if not name:
                continue
            for h in el.get("verifiedUsing", []) or []:
                if not isinstance(h, dict):
                    continue
                algo = str(h.get("algorithm", "")).lower()
                if algo in ("sha256", "sha_256"):
                    out[normalise(name)] = h.get("hashValue", "").lower()
                    break
        return out, "SPDX 3.x"

    # --- SPDX 2.x: flat files[] list -------------------------------------
    files = doc.get("files")
    if isinstance(files, list):
        for f in files:
            if not isinstance(f, dict):
                continue
            name = f.get("fileName")
            if not name:
                continue
            for c in f.get("checksums", []) or []:
                if str(c.get("algorithm", "")).upper() == "SHA256":
                    out[normalise(name)] = str(c.get("checksumValue", "")).lower()
                    break
        return out, "SPDX 2.x"

    die(f"{path}: neither an SPDX 3.x @graph nor an SPDX 2.x files[] list")


def normalise(name):
    """Normalise an SBOM file name to a comparable path."""
    n = name.strip()
    if n.startswith("./"):
        n = n[1:]
    if not n.startswith("/"):
        n = "/" + n
    return n


def classify(path):
    """Return ('image', reason) | ('volatile', reason) | ('content', '')."""
    for suf in IMAGE_LEVEL_SUFFIXES:
        if path.endswith(suf):
            return "image", "filesystem image metadata (creation time / UUID)"
    for prefix, reason in KNOWN_VOLATILE.items():
        if path.startswith(prefix):
            return "volatile", reason
    return "content", ""


def parse_kv(pairs, flag):
    out = OrderedDict()
    for p in pairs or []:
        if "=" not in p:
            die(f"{flag} expects name=sha256, got: {p}")
        k, v = p.split("=", 1)
        out[k.strip()] = v.strip().lower()
    return out


def main():
    ap = argparse.ArgumentParser(
        description="Generate a per-file reproducibility report from two builds."
    )
    ap.add_argument("--sbom-a", required=True, help="SBOM of build A")
    ap.add_argument("--sbom-b", required=True, help="SBOM of build B")
    ap.add_argument("--release", required=True, help="e.g. v2.1.0-rc7")
    ap.add_argument("--distro", required=True, help="Yocto series, e.g. wrynose")
    ap.add_argument("--machine", default="rock5a")
    ap.add_argument("--build-id-a", default="", help="build timestamp / id of A")
    ap.add_argument("--build-id-b", default="", help="build timestamp / id of B")
    ap.add_argument(
        "--artifact-a",
        action="append",
        metavar="NAME=SHA256",
        help="top-level artifact hash from build A (repeatable)",
    )
    ap.add_argument(
        "--artifact-b",
        action="append",
        metavar="NAME=SHA256",
        help="top-level artifact hash from build B (repeatable)",
    )
    ap.add_argument("--outdir", default="docs/reproducibility")
    ap.add_argument(
        "--date",
        default=datetime.date.today().isoformat(),
        help="report date (YYYY-MM-DD); defaults to today",
    )
    args = ap.parse_args()

    stamp = args.date.replace("-", "")
    base = f"{args.distro}-{stamp}"
    md_path = os.path.join(args.outdir, f"{base}.md")
    diff_path = os.path.join(args.outdir, f"{base}-file-hash-diff.txt")

    # --- history protection ------------------------------------------------
    for p in (md_path, diff_path):
        if os.path.exists(p):
            die(
                f"{p} already exists.\n"
                "       This tool never overwrites a published report. A later\n"
                "       measurement belongs in a NEW dated report beside the old\n"
                "       one; the superseded report keeps its original numbers.\n"
                "       Pass --date with the new measurement date.",
                code=2,
            )

    a, flav_a = load_file_hashes(args.sbom_a)
    b, flav_b = load_file_hashes(args.sbom_b)

    if flav_a != flav_b:
        print(
            f"warning: comparing {flav_a} against {flav_b}; file counts across "
            "SPDX generations are not comparable",
            file=sys.stderr,
        )

    keys_a, keys_b = set(a), set(b)
    only_a = sorted(keys_a - keys_b)
    only_b = sorted(keys_b - keys_a)
    common = sorted(keys_a & keys_b)

    identical = [k for k in common if a[k] == b[k]]
    differing = [k for k in common if a[k] != b[k]]

    buckets = {"image": [], "volatile": [], "content": []}
    reasons = {}
    for k in differing:
        kind, why = classify(k)
        buckets[kind].append(k)
        reasons[k] = why

    art_a = parse_kv(args.artifact_a, "--artifact-a")
    art_b = parse_kv(args.artifact_b, "--artifact-b")
    art_names = sorted(set(art_a) | set(art_b))

    # Content reproducibility is achieved iff nothing outside the image-level
    # and known-volatile buckets differs, and neither build has files the
    # other lacks.
    achieved = not buckets["content"] and not only_a and not only_b

    os.makedirs(args.outdir, exist_ok=True)

    # ---------------- diff file -------------------------------------------
    with open(diff_path, "w", encoding="utf-8") as fh:
        fh.write(f"# per-file hash differences: {args.release} ({args.distro})\n")
        fh.write(f"# build A: {args.build_id_a or 'unspecified'}\n")
        fh.write(f"# build B: {args.build_id_b or 'unspecified'}\n")
        fh.write(f"# generated: {args.date} by scripts/mk-repro-report.py\n")
        fh.write("#\n# columns: <class> <path> <sha256-A> <sha256-B> [reason]\n\n")
        for kind in ("content", "image", "volatile"):
            for k in buckets[kind]:
                r = f"  {reasons[k]}" if reasons[k] else ""
                fh.write(f"{kind:8s} {k} {a[k]} {b[k]}{r}\n")
        for k in only_a:
            fh.write(f"only-A   {k} {a[k]} -\n")
        for k in only_b:
            fh.write(f"only-B   {k} - {b[k]}\n")
        if not differing and not only_a and not only_b:
            fh.write("# no differences\n")

    # ---------------- markdown report -------------------------------------
    L = []
    w = L.append
    w(f"# Reproducibility report — {args.release} ({args.distro}, {args.machine})")
    w("")
    w(f"Generated {args.date} by `scripts/mk-repro-report.py` from two")
    w("independent builds of the same tag. Raw per-file differences:")
    w(f"`{os.path.basename(diff_path)}` (same directory).")
    w("")
    w("## Inputs")
    w("")
    w("| | Build A | Build B |")
    w("| --- | --- | --- |")
    w(f"| Build id | `{args.build_id_a or 'unspecified'}` | `{args.build_id_b or 'unspecified'}` |")
    w(f"| SBOM | `{os.path.basename(args.sbom_a)}` | `{os.path.basename(args.sbom_b)}` |")
    w(f"| SBOM format | {flav_a} | {flav_b} |")
    w(f"| Files with SHA-256 | {len(a)} | {len(b)} |")
    w("")

    if art_names:
        w("## Top-level artifacts")
        w("")
        w("| Artifact | Build A | Build B | Match |")
        w("| --- | --- | --- | --- |")
        for n in art_names:
            ha, hb = art_a.get(n, "-"), art_b.get(n, "-")
            mark = "yes" if (ha == hb and ha != "-") else "no"
            w(f"| `{n}` | `{ha[:16]}…` | `{hb[:16]}…` | {mark} |")
        w("")

    w("## Per-file result")
    w("")
    w("| Class | Count |")
    w("| --- | --- |")
    w(f"| Compared (present in both) | {len(common)} |")
    w(f"| Identical | {len(identical)} |")
    w(f"| Differing — rootfs content | {len(buckets['content'])} |")
    w(f"| Differing — image-level artifact | {len(buckets['image'])} |")
    w(f"| Differing — known volatile | {len(buckets['volatile'])} |")
    w(f"| Present only in A | {len(only_a)} |")
    w(f"| Present only in B | {len(only_b)} |")
    w("")

    if achieved:
        w("**Per-file content reproducibility: ACHIEVED.**")
        w("")
        w("Every file present in both builds has an identical SHA-256, except")
        w("entries classified as image-level artifacts or known volatile files.")
        if buckets["image"]:
            w("Image-level divergence is filesystem metadata (creation timestamp,")
            w("superblock UUID) and is not a content difference.")
        w("")
    else:
        w("**Per-file content reproducibility: NOT ACHIEVED.**")
        w("")
        if buckets["content"]:
            w(f"{len(buckets['content'])} file(s) differ in rootfs content:")
            w("")
            for k in buckets["content"][:50]:
                w(f"- `{k}`")
            if len(buckets["content"]) > 50:
                w(f"- … and {len(buckets['content']) - 50} more "
                  f"(see `{os.path.basename(diff_path)}`)")
            w("")
        if only_a or only_b:
            w(f"{len(only_a)} file(s) exist only in build A, "
              f"{len(only_b)} only in build B.")
            w("")

    if buckets["image"]:
        w("### Image-level artifacts (expected to differ)")
        w("")
        for k in buckets["image"]:
            w(f"- `{k}` — {reasons[k]}")
        w("")

    if buckets["volatile"]:
        w("### Known volatile files")
        w("")
        for k in buckets["volatile"]:
            w(f"- `{k}` — {reasons[k]}")
        w("")

    w("## Method")
    w("")
    w("File hashes are read from the SPDX documents of each build and compared")
    w("by path. No file in either build tree is read or modified by this tool.")
    w("Classification of a difference as image-level or volatile follows fixed")
    w("lists in `scripts/mk-repro-report.py`; every other difference is")
    w("reported as a content finding without interpretation.")
    w("")
    w("This report supersedes nothing. Earlier reports in this directory keep")
    w("their original figures and dates.")
    w("")

    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))

    print(f"wrote {md_path}")
    print(f"wrote {diff_path}")
    print(
        f"result: {len(identical)}/{len(common)} identical; "
        f"content differences: {len(buckets['content'])}; "
        f"reproducibility {'ACHIEVED' if achieved else 'NOT ACHIEVED'}"
    )


if __name__ == "__main__":
    main()
