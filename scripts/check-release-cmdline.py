#!/usr/bin/env python3
"""check-release-cmdline.py: the kernel command line of a release is the
expected one.

Reads components.slots.*.cmdline from a PCR reference written by
mk-pcr-reference.py (the /chosen bootargs of each slot's devicetree inside the
signed FIT, bootm path) and compares it with security/cmdline-<board>.json:

  - the set of slots is the expected one;
  - the first word is dm-mod.create with a verity table of the expected form:
    name, read-only, the slot's device as data and hash device, the expected
    block sizes and hash algorithm, a 64-hex-digit root hash, a hex salt and
    the expected options. Sizes, root hash and salt come from the build and
    are not pinned, but they must be the same in every slot;
  - every other word equals the expected list, in order, with {slot}
    replaced by the slot name. A missing, extra or reordered word fails.

A positive match, not a list of forbidden words: anything the reference does
not name is refused, including arguments nobody thought to forbid.

Usage:
  check-release-cmdline.py --reference security/cmdline-rock5a.json \\
      --pcr pcr-reference-rock5a.json

Exit status 0 when every slot matches, 1 otherwise. Reads two files and
changes nothing.
"""

import argparse
import json
import re
import shlex
import sys

HEX64 = re.compile(r'^[0-9a-f]{64}$')
HEX = re.compile(r'^[0-9a-f]+$')
UINT = re.compile(r'^[0-9]+$')


def check_verity(table, slot, dev, ref):
    """Problems with one dm-mod.create table, and the build-specific values
    (sectors, blocks, root hash, salt) for the cross-slot comparison."""
    v = ref['verity']
    problems = []
    head, sep, target = table.partition(',0 ')
    if not sep:
        return ['dm-mod.create is not "<name>,<uuid>,<minor>,<flags>,0 <table>": %r'
                % table], None
    want_head = '%s,,,ro' % v['name']
    if head != want_head:
        problems.append('dm-mod.create device spec is %r, expected %r' % (head, want_head))
    f = target.split()
    # <sectors> verity 1 <data_dev> <hash_dev> <dbs> <hbs> <dblocks> <hstart>
    # <alg> <root_hash> <salt> <n_opts> <opts...>
    if len(f) < 13:
        return problems + ['verity table has %d fields, expected at least 13: %r'
                           % (len(f), target)], None
    sectors, kind, version, ddev, hdev, dbs, hbs, dblocks, hstart, alg, root, salt, nopt = f[:13]
    opts = f[13:]
    if not UINT.match(sectors):
        problems.append('verity length %r is not a number' % sectors)
    if kind != 'verity' or version != '1':
        problems.append('target is %r version %r, expected verity version 1' % (kind, version))
    if ddev != dev or hdev != dev:
        problems.append('slot %s data/hash devices are %s/%s, expected %s'
                        % (slot, ddev, hdev, dev))
    if dbs != str(v['data_block_size']) or hbs != str(v['hash_block_size']):
        problems.append('block sizes %s/%s, expected %s/%s'
                        % (dbs, hbs, v['data_block_size'], v['hash_block_size']))
    if not (UINT.match(dblocks) and UINT.match(hstart)):
        problems.append('data blocks %r / hash start %r are not numbers' % (dblocks, hstart))
    if alg != v['hash_algorithm']:
        problems.append('hash algorithm %r, expected %r' % (alg, v['hash_algorithm']))
    if not HEX64.match(root):
        problems.append('root hash %r is not 64 hex digits' % root)
    if not HEX.match(salt):
        problems.append('salt %r is not hex' % salt)
    if nopt != str(len(opts)) or opts != v['options']:
        problems.append('options %s %s, expected %d %s'
                        % (nopt, ' '.join(opts), len(v['options']), ' '.join(v['options'])))
    return problems, (sectors, dblocks, hstart, root, salt)


def check(ref, pcr):
    problems = []
    slots = pcr.get('components', {}).get('slots')
    if not isinstance(slots, dict) or not slots:
        return ['no components.slots in the PCR reference (not the bootm path?)']
    want = set(ref['slots'])
    if set(slots) != want:
        problems.append('slots are %s, expected %s' % (sorted(slots), sorted(want)))
    build_values = {}
    for slot in sorted(set(slots) & want):
        cmdline = slots[slot].get('cmdline', '')
        try:
            words = shlex.split(cmdline)
        except ValueError as e:
            problems.append('slot %s: command line does not parse (%s): %r' % (slot, e, cmdline))
            continue
        if not words or not words[0].startswith('dm-mod.create='):
            problems.append('slot %s: first word is not dm-mod.create: %r'
                            % (slot, words[0] if words else ''))
            continue
        vp, values = check_verity(words[0][len('dm-mod.create='):], slot,
                                  ref['slots'][slot]['device'], ref)
        problems += ['slot %s: %s' % (slot, p) for p in vp]
        if values is not None:
            build_values[slot] = values
        got = words[1:]
        expected = [a.replace('{slot}', slot) for a in ref['args']]
        if got != expected:
            extra = [w for w in got if w not in expected]
            missing = [w for w in expected if w not in got]
            detail = []
            if extra:
                detail.append('not expected: %s' % ' '.join(extra))
            if missing:
                detail.append('missing: %s' % ' '.join(missing))
            if not detail:
                detail.append('same words in a different order')
            problems.append('slot %s: arguments differ (%s)\n    got:      %s\n    expected: %s'
                            % (slot, '; '.join(detail), ' '.join(got), ' '.join(expected)))
    if len(set(build_values.values())) > 1:
        problems.append('verity length, blocks, root hash or salt differ between slots: %s'
                        % ', '.join('%s=%s' % (s, v[3][:16]) for s, v in sorted(build_values.items())))
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--reference', required=True, help='security/cmdline-<board>.json')
    ap.add_argument('--pcr', required=True, help='pcr-reference-<board>.json')
    a = ap.parse_args(argv)
    with open(a.reference) as f:
        ref = json.load(f)
    with open(a.pcr) as f:
        pcr = json.load(f)
    problems = check(ref, pcr)
    if problems:
        for p in problems:
            print('check-release-cmdline: %s' % p, file=sys.stderr)
        return 1
    for slot in sorted(ref['slots']):
        print('    slot %s: command line matches %s' % (slot, a.reference.split('/')[-1]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
