#!/usr/bin/env python3
"""Tests for scripts/check-release-cmdline.py.

The positive case is the command line of the published v2.1.0-rc14 release
(components.slots of its pcr-reference-rock5a.json, kept here as
pcr-slots-v2.1.0-rc14.json). Each negative case changes that real command
line in one way and must be refused.
"""

import copy
import importlib.util
import json
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
spec = importlib.util.spec_from_file_location(
    'check_release_cmdline', os.path.join(ROOT, 'scripts', 'check-release-cmdline.py'))
crc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(crc)

with open(os.path.join(ROOT, 'security', 'cmdline-rock5a.json')) as f:
    REF = json.load(f)
with open(os.path.join(HERE, 'pcr-slots-v2.1.0-rc14.json')) as f:
    RC14 = json.load(f)


def edited(fn, slots=('A', 'B')):
    p = copy.deepcopy(RC14)
    for s in slots:
        c = p['components']['slots'][s]
        c['cmdline'] = fn(c['cmdline'])
    return p


class CheckReleaseCmdline(unittest.TestCase):

    def refused(self, pcr, needle):
        problems = crc.check(REF, pcr)
        self.assertTrue(problems, 'expected a refusal')
        self.assertTrue(any(needle in p for p in problems),
                        'no problem mentions %r: %s' % (needle, problems))

    def test_rc14_release_matches(self):
        self.assertEqual(crc.check(REF, RC14), [])

    def test_rc10_case_ima_appraise_appended(self):
        # What the dev-policy axis did to rc10: arguments appended at the end.
        self.refused(edited(lambda c: c + ' ima_appraise=enforce ima_policy=appraise_tcb'),
                     'not expected: ima_appraise=enforce ima_policy=appraise_tcb')

    def test_extra_argument_in_one_slot(self):
        self.refused(edited(lambda c: c + ' init=/bin/sh', slots=('B',)),
                     'slot B: arguments differ')

    def test_missing_argument(self):
        self.refused(edited(lambda c: c.replace(' panic=5', '')), 'missing: panic=5')

    def test_console_order(self):
        self.refused(edited(lambda c: c.replace('console=tty1 console=ttyS2,1500000n8',
                                                'console=ttyS2,1500000n8 console=tty1')),
                     'different order')

    def test_wrong_slot_name(self):
        self.refused(edited(lambda c: c.replace('rauc.slot=B', 'rauc.slot=A'), slots=('B',)),
                     'slot B: arguments differ')

    def test_wrong_device(self):
        self.refused(edited(lambda c: c.replace('mmcblk0p4', 'mmcblk1p4'), slots=('B',)),
                     'expected /dev/mmcblk0p4')

    def test_root_hash_differs_between_slots(self):
        self.refused(edited(lambda c: c.replace('02a7d9be', '12a7d9be'), slots=('B',)),
                     'differ between slots')

    def test_no_verity(self):
        self.refused(edited(lambda c: c.split('" ', 1)[1].replace('root=/dev/dm-0',
                                                                  'root=/dev/mmcblk0p2')),
                     'first word is not dm-mod.create')

    def test_writable_mapping(self):
        self.refused(edited(lambda c: c.replace('rootfs,,,ro,', 'rootfs,,,rw,')),
                     'device spec')

    def test_verity_option_dropped(self):
        self.refused(edited(lambda c: c.replace(' 1 ignore_zero_blocks"', ' 0"')), 'options')

    def test_missing_slot(self):
        p = copy.deepcopy(RC14)
        del p['components']['slots']['B']
        self.refused(p, 'slots are')

    def test_extlinux_reference_refused(self):
        self.refused({'components': {}}, 'no components.slots')


if __name__ == '__main__':
    unittest.main(verbosity=2)
