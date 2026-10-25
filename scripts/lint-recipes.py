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

Each recipe is linted in its own oelint-adv process, together with the
.bbappend files that apply to it; .bbappend files with no recipe in this
repository are linted per target name. One process over all files is not
deterministic: oelint-adv hands groups of files to worker processes, and
state left behind by one group (machine names it learned from a BSP layer,
for one) changes the findings of the next group in the same worker. Which
groups share a worker depends on the number of CPUs, so the same tree gave
different findings on a two-CPU host and on CI. Separate processes keep
every finding a function of the files it is about.

Needs: oelint-adv at the version pinned in CI (OELINT_ADV in ci.yml).
"""
import collections
import concurrent.futures
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BASELINE = os.path.join(ROOT, "tests", "lint", "oelint-baseline.txt")
LINE = re.compile(r"^(?P<file>.+?):(?P<line>\d+):error:(?P<rule>[^:]+):")
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


def groups(files):
    """Recipe groups as BitBake applies them: each .bb with the .bbappend
    files whose name matches it ('%' as a wildcard), and the remaining
    .bbappend files grouped by the name they append to."""
    bbs = [f for f in files if f.endswith(".bb")]
    appends = [f for f in files if f.endswith(".bbappend")]
    out = {bb: [bb] for bb in bbs}
    lone = {}
    for a in appends:
        stem = os.path.basename(a)[:-len(".bbappend")]
        pat = re.compile("^" + re.escape(stem).replace("%", ".*") + r"\.bb$")
        hits = [bb for bb in bbs if pat.match(os.path.basename(bb))]
        for bb in hits:
            out[bb].append(a)
        if not hits:
            lone.setdefault(stem.replace("%", ""), []).append(a)
    return sorted(out.values()) + sorted(lone.values())


def lint_group(files):
    p = subprocess.run(["oelint-adv", "--quiet", "--jobs", "1", *files],
                       capture_output=True, text=True, cwd=ROOT, check=False)
    if p.returncode not in (0, 1):
        sys.exit(f"lint-recipes: oelint-adv failed (exit {p.returncode}) on "
                 f"{' '.join(files)}:\n{p.stderr}")
    return (p.stdout + p.stderr).splitlines()


def current():
    with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 1) as pool:
        outputs = list(pool.map(lint_group, groups(recipes())))
    # A file can be reached from several groups: a .bbappend that applies to
    # several recipes, or a recipe that another one requires. Count a finding
    # once per file, line and rule. The message text cannot be the key: it
    # names the group's files in set order, which differs between processes.
    seen = set()
    roots = layer_roots()
    for out in outputs:
        for line in out:
            r = REQUIRE.match(line)
            if r and found_along_bbpath(r["inc"], roots):
                continue
            m = LINE.match(line)
            if m:
                f = os.path.relpath(os.path.abspath(os.path.join(ROOT, m["file"])), ROOT)
                seen.add((f, int(m["line"]), m["rule"]))
    return collections.Counter((f, rule) for f, _, rule in seen)


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
