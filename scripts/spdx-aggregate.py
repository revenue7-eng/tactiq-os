#!/usr/bin/env python3
"""
spdx-aggregate.py — merge per-package SPDX 2.2 documents from a Yocto image
SPDX archive into a single aggregate JSON document, matching the rc3 release
artifact format.

Usage:
  spdx-aggregate.py <input-dir> <output-file> <release-tag> <image-name>
"""

import datetime
import json
import pathlib
import sys


def main():
    if len(sys.argv) != 5:
        print(
            "usage: spdx-aggregate.py <input-dir> <output-file> "
            "<release-tag> <image-name>",
            file=sys.stderr,
        )
        sys.exit(2)

    input_dir = pathlib.Path(sys.argv[1])
    output_file = pathlib.Path(sys.argv[2])
    release_tag = sys.argv[3]
    image_name = sys.argv[4]

    if not input_dir.is_dir():
        print(f"error: {input_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    sources = sorted(input_dir.glob("*.spdx.json"))
    if not sources:
        print(f"error: no *.spdx.json files in {input_dir}", file=sys.stderr)
        sys.exit(1)

    seen_packages = set()
    seen_files = set()

    out_packages = []
    out_files = []
    out_relationships = []

    for src_path in sources:
        with src_path.open("r", encoding="utf-8") as fh:
            doc = json.load(fh)

        for pkg in doc.get("packages", []):
            spdxid = pkg.get("SPDXID")
            if spdxid and spdxid not in seen_packages:
                seen_packages.add(spdxid)
                out_packages.append(pkg)

        for f in doc.get("files", []):
            spdxid = f.get("SPDXID")
            if spdxid and spdxid not in seen_files:
                seen_files.add(spdxid)
                out_files.append(f)

        # relationships are concatenated without deduplication
        # to preserve rc3 release format (51284 total, only 20 byte-identical
        # duplicates kept).
        out_relationships.extend(doc.get("relationships", []))

    timestamp = datetime.datetime.now(datetime.timezone.utc)
    timestamp_iso = timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
    timestamp_compact = timestamp.strftime("%Y%m%dT%H%M%SZ")

    namespace = (
        f"https://github.com/revenue7-eng/tactiq-os/sbom/"
        f"{release_tag}/aggregate-{timestamp_compact}"
    )

    aggregate = {
        "SPDXID": "SPDXRef-DOCUMENT",
        "creationInfo": {
            "comment": (
                "Aggregate SPDX 2.2 document built by merging per-package "
                "SPDX documents from the Yocto image archive."
            ),
            "created": timestamp_iso,
            "creators": [
                "Tool: yocto-create-spdx",
                "Tool: tactiq-aggregate-script-1.0",
            ],
            "licenseListVersion": "3.22",
        },
        "dataLicense": "CC0-1.0",
        "documentNamespace": namespace,
        "files": out_files,
        "name": f"{image_name}-aggregate",
        "packages": out_packages,
        "relationships": out_relationships,
        "spdxVersion": "SPDX-2.2",
    }

    with output_file.open("w", encoding="utf-8") as fh:
        json.dump(aggregate, fh, indent=2, sort_keys=False)
        fh.write("\n")

    print(
        f"wrote {output_file}: "
        f"{len(out_packages)} packages, "
        f"{len(out_files)} files, "
        f"{len(out_relationships)} relationships",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
