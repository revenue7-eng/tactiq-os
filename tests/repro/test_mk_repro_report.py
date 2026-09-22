#!/usr/bin/env python3
"""Regression test for scripts/mk-repro-report.py.

What this guards, and why it exists
-----------------------------------
The report generator writes a document that is published and read as
evidence. Every failure mode below produced, at some point, a report that
looked complete and said more than had been measured: an empty comparison
verdicted ACHIEVED, two absent hashes comparing equal as identical, a file
dropped from the comparison because its SBOM entry carried no SHA-256.

Those were fixed by hand. This test is what turns red when they come back,
or when a new SBOM shape introduces the same shape of hole: the point is not
that today's values line up, it is that the build fails when they stop
lining up.

Run: python3 tests/repro/test_mk_repro_report.py
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GEN = REPO / "scripts" / "mk-repro-report.py"

H1 = "a" * 64
H2 = "b" * 64

failures = []
checks = 0


def spdx3(files):
    """files: list of (name, hash_value_or_None). None = entry without SHA-256."""
    graph = []
    for name, value in files:
        el = {"type": "software_File", "name": name, "spdxId": f"spdx:{name}"}
        if value is not None:
            el["verifiedUsing"] = [{"algorithm": "sha256", "hashValue": value}]
        graph.append(el)
    return {"@graph": graph}


def spdx2(files):
    out = []
    for name, value in files:
        f = {"fileName": name, "SPDXID": f"SPDXRef-{name}"}
        if value is not None:
            f["checksums"] = [{"algorithm": "SHA256", "checksumValue": value}]
        out.append(f)
    return {"files": out}


def run(doc_a, doc_b, extra=(), date="2026-01-01"):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "a.json").write_text(json.dumps(doc_a))
        (tmp / "b.json").write_text(json.dumps(doc_b))
        cmd = [
            sys.executable, str(GEN),
            "--sbom-a", str(tmp / "a.json"),
            "--sbom-b", str(tmp / "b.json"),
            "--release", "test", "--distro", "test",
            "--outdir", str(tmp / "out"), "--date", date,
            *extra,
        ]
        p = subprocess.run(cmd, capture_output=True, text=True)
        report = tmp / "out" / "test-20260101.md"
        body = report.read_text() if report.exists() else ""
        return p.returncode, p.stdout + p.stderr, body


def check(label, condition, detail=""):
    global checks
    checks += 1
    if condition:
        print(f"ok   {label}")
    else:
        print(f"FAIL {label}{(': ' + detail) if detail else ''}")
        failures.append(label)


def main():
    if not GEN.is_file():
        print(f"FAIL generator not found: {GEN}")
        return 1

    good = [("/bin/x", H1), ("/bin/y", H2)]

    # A comparison that should succeed, so a failure below means the test
    # harness is wrong rather than the script.
    rc, out, body = run(spdx3(good), spdx3(good))
    check("identical SBOMs report ACHIEVED",
          rc == 0 and "reproducibility: ACHIEVED" in body, out)
    check("identical SBOMs count both files", "| Compared (present in both) | 2 |" in body)

    rc, out, body = run(spdx3(good), spdx3([("/bin/x", H1), ("/bin/y", H1)]))
    check("a differing hash is NOT ACHIEVED",
          rc == 0 and "reproducibility: NOT ACHIEVED" in body, out)

    # Missing hash values must not compare equal to each other.
    empty = [("/bin/x", "")] * 1
    rc, out, _ = run(spdx3(empty), spdx3(empty))
    check("empty hash value stops the run", rc != 0, out)

    rc, out, body = run(spdx3([("/bin/x", None)]), spdx3([("/bin/x", None)]))
    check("entry without SHA-256 does not silently vanish",
          rc != 0 or "reproducibility: NOT ACHIEVED" in body, out)

    rc, out, body = run(spdx2([("/bin/x", None)]), spdx2([("/bin/x", None)]))
    check("SPDX 2.x entry without SHA-256 does not silently vanish",
          rc != 0 or "reproducibility: NOT ACHIEVED" in body, out)

    rc, out, _ = run(spdx3([("/bin/x", "zz")]), spdx3([("/bin/x", "zz")]))
    check("malformed hash value stops the run", rc != 0, out)

    rc, out, body = run(spdx3(good + [("/bin/z", None)]),
                        spdx3(good + [("/bin/z", None)]))
    check("file without SHA-256 blocks ACHIEVED",
          "reproducibility: NOT ACHIEVED" in body, out)
    check("file without SHA-256 is counted in the report",
          "| Files listed without SHA-256 | 1 | 1 |" in body)

    # Nothing compared must never read as success.
    rc, out, _ = run(spdx3([("/bin/x", H1)]), spdx3([("/bin/z", H1)]))
    check("no common file stops the run", rc != 0, out)

    rc, out, _ = run({"@graph": []}, {"@graph": []})
    check("empty SPDX graph stops the run", rc != 0, out)

    rc, out, _ = run({"@graph": [{"type": "software_Package", "name": "p"}]},
                     {"@graph": [{"type": "software_Package", "name": "p"}]})
    check("graph with no software_File stops the run", rc != 0, out)

    rc, out, _ = run({"files": []}, {"files": []})
    check("empty SPDX 2.x file list stops the run", rc != 0, out)

    rc, out, body = run(spdx2(good), spdx2(good))
    check("SPDX 2.x pair is read and compared",
          rc == 0 and "| SBOM format | SPDX 2.x | SPDX 2.x |" in body, out)

    # Top-level artifacts.
    rc, out, _ = run(spdx3(good), spdx3(good),
                     extra=["--artifact-a", "img=", "--artifact-b", "img="])
    check("empty artifact hash stops the run", rc != 0, out)

    rc, out, body = run(spdx3(good), spdx3(good),
                        extra=["--artifact-a", f"img={H1}",
                               "--artifact-b", f"img={H2}"])
    check("differing artifact hashes report no match", "| no |" in body, body)

    # Caveats and exclusions must reach the document, not only the terminal.
    rc, out, body = run(spdx3(good), spdx3(good),
                        extra=["--caveat", "forced run"])
    check("a caveat appears in the report", "forced run" in body, body)

    rc, out, body = run(spdx3(good), spdx3(good),
                        extra=["--artifact-a", f"img={H1}",
                               "--artifact-b", f"img={H1}",
                               "--artifact-excluded", "copied.py=identical by construction"])
    check("an excluded artifact is named in the report",
          "copied.py" in body and "identical by construction" in body, body)

    print(f"\n{checks - len(failures)}/{checks} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
