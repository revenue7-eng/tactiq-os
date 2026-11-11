#!/usr/bin/env python3
"""The release IMA policy measures exactly what the development policy measures.

recipes-security/ima-policy/files/ holds two policies:

  tactiq-ima-appraise.policy  development image (ima-evm-rootfs): appraisal
                              under the in-tree IMA key, then measurement;
  tactiq-ima-measure.policy   release image (tactiq-ima-measure-policy):
                              measurement only.

A reference value for PCR 10, 11 or 12 taken on one image is meant to hold
on the other, so the measurement rules are one decision kept in two files.
This test is what keeps it one decision: the measure and dont_measure rules
of both files must be the same lines in the same order (IMA takes the first
matching rule, so order is part of the policy). It also refuses any appraise
or dont_appraise rule in the release policy: that image is not signed, and
an appraise rule there refuses its own files.

Run: python3 tests/ima/test_ima_policies.py
"""

import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
DIR = os.path.join(ROOT, 'recipes-security', 'ima-policy', 'files')
DEV = os.path.join(DIR, 'tactiq-ima-appraise.policy')
REL = os.path.join(DIR, 'tactiq-ima-measure.policy')

failures = []


def check(name, ok, detail=''):
    if not ok:
        failures.append(f'{name}: {detail}' if detail else name)


def rules(path):
    """Policy lines that are rules: not blank, not a comment."""
    with open(path, encoding='utf-8') as f:
        return [l.strip() for l in f if l.strip() and not l.lstrip().startswith('#')]


def action(rule):
    return rule.split()[0]


def compare(dev, rel):
    """Problems between a development and a release rule list."""
    out = []
    dev_measure = [r for r in dev if action(r) in ('measure', 'dont_measure')]
    rel_measure = [r for r in rel if action(r) in ('measure', 'dont_measure')]
    if not rel_measure:
        out.append('release policy has no measure rule')
    if dev_measure != rel_measure:
        for i, (a, b) in enumerate(zip(dev_measure + [None] * len(rel_measure),
                                       rel_measure + [None] * len(dev_measure))):
            if a != b:
                out.append(f'measurement rule {i + 1} differs: development {a!r}, release {b!r}')
                break
    other = [r for r in rel if action(r) not in ('measure', 'dont_measure')]
    for r in other:
        out.append(f'release policy has a rule other than measurement: {r!r}')
    return out


def main():
    dev, rel = rules(DEV), rules(REL)
    check('development policy has appraise rules',
          any(action(r) == 'appraise' for r in dev))
    problems = compare(dev, rel)
    check('the two policies measure the same', not problems, '; '.join(problems))

    # The comparison itself must be able to fail.
    m = [i for i, r in enumerate(rel) if action(r) == 'measure']
    check('a missing release rule is caught', compare(dev, rel[:m[-1]] + rel[m[-1] + 1:]))
    check('a changed release rule is caught',
          compare(dev, [r + ' pcr=13' if i == m[0] else r for i, r in enumerate(rel)]))
    check('a reordered release rule is caught',
          compare(dev, rel[:m[0]] + [rel[m[1]], rel[m[0]]] + rel[m[1] + 1:]))
    check('an appraise rule in the release is caught',
          compare(dev, rel + ['appraise func=BPRM_CHECK appraise_type=imasig']))
    check('a dont_appraise rule in the release is caught',
          compare(dev, ['dont_appraise fsmagic=0x9fa0'] + rel))
    check('an empty release policy is caught', compare(dev, []))

    print(f'{len(failures)} failed')
    for f in failures:
        print(f'FAIL {f}')
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()
