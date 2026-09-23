#!/usr/bin/env python3
"""check-known-issues.py: every issue the previous release left open must
reappear in this release's coverage manifest, still deferred or resolved.

Usage: check-known-issues.py <repo-root> <board> <tag>

Schema 0.3 of security/coverage-<board>.<tag>.yaml carries, under manifest:

  known_issues:
    previous: "v2.1.0-rc11"        # the release this one follows
    deferred:                      # open in this release
      - id: kernel-pin             # [a-z0-9-]+, stable across releases
        text: "..."                # free text, may be reworded
    resolved:                      # closed since `previous`
      - id: release-identity
        text: "..."

The id is what carries an issue from one release to the next; the text may
change. Every id in the previous release's `deferred` must appear in this
release's `deferred` or `resolved`, or the release is not assembled. The
previous release is read from security/coverage-<board>.<previous>.yaml when
that manifest is schema 0.3 or later, else from
security/known-issues-baseline-<board>.<previous>.yaml, written once for the
last release before ids existed.

Why: v2.1.0-rc11 dropped an open issue from its manifest silently. The lists
were carried by copying (rc10 still used the key deferred_in_rc7) and nothing
compared one release with the next (docs/release-notes/v2.1.0-rc11-errata.md).
"""
import re
import sys

import yaml

# Manifests written before ids existed. They are not checked; any other tag
# must be schema 0.3 or later.
LEGACY_TAGS = {"v2.1.0-rc5", "v2.1.0-rc6", "v2.1.0-rc7", "v2.1.0-rc10", "v2.1.0-rc11"}
LAST_LEGACY = "v2.1.0-rc11"
ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def version(s):
    return tuple(int(x) for x in str(s).split("."))


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        return None


def items(block, name, where, errors):
    """Validate one list of {id, text} entries; return {id: text}."""
    out = {}
    lst = block.get(name)
    if lst is None:
        return out
    if not isinstance(lst, list):
        errors.append(f"{where}: {name} is not a list")
        return out
    for i, it in enumerate(lst):
        if not isinstance(it, dict) or set(it) != {"id", "text"}:
            errors.append(f"{where}: {name}[{i}] must have exactly the keys id and text")
            continue
        iid, text = it["id"], it["text"]
        if not isinstance(iid, str) or not ID_RE.match(iid):
            errors.append(f"{where}: {name}[{i}] id {iid!r} is not [a-z0-9-]+")
            continue
        if not isinstance(text, str) or not text.strip():
            errors.append(f"{where}: {name}[{i}] ({iid}) has no text")
        if iid in out:
            errors.append(f"{where}: {name} repeats id {iid}")
        out[iid] = text
    return out


def main():
    if len(sys.argv) != 4:
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    repo, board, tag = sys.argv[1:]
    sec = f"{repo}/security"
    new_path = f"{sec}/coverage-{board}.{tag}.yaml"
    new = load(new_path)
    if new is None:
        print(f"::error:: manifest not found: {new_path}", file=sys.stderr)
        return 1

    schema = new.get("schema_version")
    if tag in LEGACY_TAGS:
        print(f"    {tag} predates known-issue ids (schema {schema}); continuity not checked")
        return 0
    if schema is None or version(schema) < (0, 3):
        print(f"::error:: {new_path}: schema_version {schema!r}; 0.3 or later is required "
              f"after {LAST_LEGACY}", file=sys.stderr)
        return 1

    errors = []
    ki = (new.get("manifest") or {}).get("known_issues")
    if not isinstance(ki, dict):
        print(f"::error:: {new_path}: manifest.known_issues missing", file=sys.stderr)
        return 1
    prev_tag = ki.get("previous")
    if not isinstance(prev_tag, str) or not prev_tag:
        errors.append(f"{new_path}: manifest.known_issues.previous missing")
    deferred = items(ki, "deferred", new_path, errors)
    resolved = items(ki, "resolved", new_path, errors)
    for iid in sorted(set(deferred) & set(resolved)):
        errors.append(f"{new_path}: {iid} is both deferred and resolved")
    if errors:
        for e in errors:
            print(f"::error:: {e}", file=sys.stderr)
        return 1

    prev_path = f"{sec}/coverage-{board}.{prev_tag}.yaml"
    prev = load(prev_path)
    if prev is not None and version(prev.get("schema_version", "0")) >= (0, 3):
        src = prev_path
        prev_ki = (prev.get("manifest") or {}).get("known_issues") or {}
    else:
        src = f"{sec}/known-issues-baseline-{board}.{prev_tag}.yaml"
        prev_ki = load(src)
        if prev_ki is None:
            print(f"::error:: previous release {prev_tag}: neither a schema 0.3 manifest "
                  f"nor {src} exists", file=sys.stderr)
            return 1
    prev_deferred = items(prev_ki, "deferred", src, errors)
    if errors:
        for e in errors:
            print(f"::error:: {e}", file=sys.stderr)
        return 1

    missing = [i for i in prev_deferred if i not in deferred and i not in resolved]
    for iid in missing:
        print(f"::error:: open at {prev_tag}, absent from {tag}: {iid}: {prev_deferred[iid]}",
              file=sys.stderr)
    if missing:
        print(f"::error:: {len(missing)} known issue(s) dropped; list each under "
              f"manifest.known_issues.deferred or .resolved with the same id", file=sys.stderr)
        return 1

    carried = [i for i in prev_deferred if i in deferred]
    closed = [i for i in prev_deferred if i in resolved]
    new_open = [i for i in deferred if i not in prev_deferred]
    print(f"    known issues vs {prev_tag}: {len(carried)} carried, {len(closed)} resolved, "
          f"{len(new_open)} new ({src.rsplit('/', 1)[1]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
