#!/usr/bin/env python3
"""lint-recipes.py: oelint-adv over every recipe and append, against a baseline.

The recipe lint used to run with --fix on two directories and could not fail.
This runs on every .bb and .bbappend in the repository and compares the
errors with tests/lint/oelint-baseline.txt, which records the errors already
known, as one "<file> <rule> <count>" line per file and rule. Line numbers are
left out on purpose, so editing a file does not move its known findings.

  lint-recipes.py            fail if any file and rule has more errors than
                             the baseline (a new error) or fewer (a fixed error
                             the baseline still lists)
  lint-recipes.py --update   rewrite the baseline from the current tree

A fixed error fails too, until the baseline is lowered with --update in the
same pull request. The baseline then always matches the tree, and a linter
that stops reporting (a broken install, a changed output format) shows as
every error "fixed" instead of passing quietly. Warnings and info lines are
not gated.

A require that oelint-adv reports as not found is checked once more along
the layer roots of this repository, the part of BBPATH the repository itself
provides. oelint-adv looks only in the recipe's directory and its own layer
root, so a BSP recipe that requires a file from the common layer would
otherwise fail although BitBake finds it. The finding is dropped only when
the file exists under one of those roots.

Needs: oelint-adv at the version pinned in CI (OELINT_ADV in ci.yml).
"""
import collections
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BASELINE = os.path.join(ROOT, "tests", "lint", "oelint-baseline.txt")
LINE = re.compile(r"^(?P<file>.+?):\d+:error:(?P<rule>[^:]+):")
REQUIRE = re.compile(r"^.+?:\d+:error:oelint\.file\.requirenotfound:'(?P<inc>[^']+)' was not found")


def recipes():
    out = []
    for d, dirs, files in os.walk(ROOT):
        dirs[:] = [x for x in dirs if not x.startswith(".") and x != "tests"]
        out += [os.path.join(d, f) for f in files if f.endswith((".bb", ".bbappend"))]
    return sorted(out)


def layer_roots():
    out = []
    for d, dirs, files in os.walk(ROOT):
        dirs[:] = [x for x in dirs if not x.startswith(".") and x != "tests"]
        if os.path.isfile(os.path.join(d, "conf", "layer.conf")):
            out.append(d)
    return sorted(out)


def found_along_bbpath(inc, roots):
    if "${" in inc or os.path.isabs(inc):
        return False
    return any(os.path.isfile(os.path.join(r, inc)) for r in roots)


def current():
    p = subprocess.run(["oelint-adv", "--quiet", *recipes()],
                       capture_output=True, text=True, cwd=ROOT, check=False)
    counts = collections.Counter()
    roots = layer_roots()
    for line in (p.stdout + p.stderr).splitlines():
        r = REQUIRE.match(line)
        if r and found_along_bbpath(r["inc"], roots):
            continue
        m = LINE.match(line)
        if m:
            f = os.path.relpath(os.path.abspath(os.path.join(ROOT, m["file"])), ROOT)
            counts[(f, m["rule"])] += 1
    if not counts and p.returncode not in (0, 1):
        sys.exit(f"lint-recipes: oelint-adv failed (exit {p.returncode}):\n{p.stderr}")
    return counts


def load():
    counts = collections.Counter()
    if os.path.exists(BASELINE):
        with open(BASELINE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    path, rule, n = line.split()
                    counts[(path, rule)] = int(n)
    return counts


def save(counts):
    with open(BASELINE, "w", encoding="utf-8") as out:
        out.write("# Known oelint-adv errors: <file> <rule> <count>. "
                  "Regenerate with scripts/lint-recipes.py --update.\n")
        for (f, rule), n in sorted(counts.items()):
            out.write(f"{f} {rule} {n}\n")


def main():
    now = current()
    if "--update" in sys.argv[1:]:
        save(now)
        print(f"baseline written: {sum(now.values())} errors in {len(now)} file/rule pairs")
        return 0
    base = load()
    new = {k: n - base[k] for k, n in now.items() if n > base[k]}
    fixed = {k: base[k] - now[k] for k in base if now[k] < base[k]}
    for (f, rule), n in sorted(new.items()):
        print(f"NEW    {f} {rule} +{n}")
    for (f, rule), n in sorted(fixed.items()):
        print(f"FIXED  {f} {rule} -{n} (run scripts/lint-recipes.py --update and commit the baseline)")
    print(f"errors: {sum(now.values())} now, {sum(base.values())} in baseline, "
          f"{sum(new.values())} new, {sum(fixed.values())} fixed")
    return 1 if new or fixed else 0


if __name__ == "__main__":
    sys.exit(main())
