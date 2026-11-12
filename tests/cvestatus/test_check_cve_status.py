#!/usr/bin/env python3
"""Tests for scripts/check-cve-status.py.

The status file is the real one in the tree. SBOMs are small SPDX 3
documents written here, with source names shaped like the linux-yocto ones
("linux-yocto/<path>"). Each failing case is an input the check must refuse.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
SCRIPT = os.path.join(ROOT, 'scripts', 'check-cve-status.py')
STATUS = os.path.join(ROOT, 'conf', 'distro', 'include', 'tactiq-cve-status.inc')

BASE = ['kernel/fork.c', 'kernel/sched/core.c', 'fs/ext4/inode.c',
        'net/ipv4/tcp.c', 'arch/arm64/kernel/setup.c']


def spdx(files, purpose='source'):
    graph = [{'type': 'software_File', 'name': 'linux-yocto/' + f,
              'software_primaryPurpose': purpose} for f in files]
    graph.append({'type': 'software_Package', 'name': 'linux-yocto'})
    return {'@context': 'https://spdx.org/rdf/3.0.1/spdx-context.jsonld', '@graph': graph}


class CheckCveStatus(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, content):
        p = os.path.join(self.tmp.name, name)
        with open(p, 'w') as f:
            f.write(content if isinstance(content, str) else json.dumps(content))
        return p

    def run_check(self, *args, status=STATUS):
        r = subprocess.run([sys.executable, '-I', SCRIPT, '--status', status, *args],
                           capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    # passes

    def test_static_real_status_file(self):
        rc, out = self.run_check('--static')
        self.assertEqual(rc, 0, out)

    def test_nothing_named_is_compiled(self):
        rc, out = self.run_check('--spdx', self.write('s.json', spdx(BASE)))
        self.assertEqual(rc, 0, out)

    def test_build_files_of_disabled_code_do_not_count(self):
        # Seen in the real SBOM: make reads Makefile and Kconfig of fs/jfs,
        # drivers/infiniband and others with that code switched off.
        files = BASE + ['fs/jfs/Makefile', 'fs/jfs/Kconfig', 'net/rose/Makefile',
                        'drivers/infiniband/Kbuild', 'drivers/infiniband/README',
                        'arch/arm64/kvm/.gitignore',
                        'arch/arm64/kvm/hyp/nvhe/hyp.lds.S']
        rc, out = self.run_check('--spdx', self.write('s.json', spdx(files)))
        self.assertEqual(rc, 0, out)

    def test_header_under_not_built_directory_fails(self):
        rc, out = self.run_check('--spdx', self.write('s.json', spdx(BASE + ['net/smc/smc.h'])))
        self.assertEqual(rc, 1, out)
        self.assertIn('CVE-2022-0400', out)

    def test_assembly_under_not_built_directory_fails(self):
        rc, out = self.run_check('--spdx', self.write('s.json', spdx(BASE + ['arch/arm64/kvm/hyp/entry.S'])))
        self.assertEqual(rc, 1, out)
        self.assertIn('CVE-2026-63941', out)

    def test_similar_name_is_not_a_match(self):
        # fs/erofs is named; fs/erofsx and net/xdp_extra are other directories.
        files = BASE + ['fs/erofsx/a.c', 'net/xdp_extra/b.c', 'kernel/sched/ext_idle.c']
        rc, out = self.run_check('--spdx', self.write('s.json', spdx(files)))
        self.assertEqual(rc, 0, out)

    # refusals

    def test_directory_entry_fails_when_its_code_is_built(self):
        rc, out = self.run_check('--spdx', self.write('s.json', spdx(BASE + ['fs/erofs/super.c'])))
        self.assertEqual(rc, 1, out)
        self.assertIn('CVE-2026-80899', out)
        self.assertIn('fs/erofs/super.c', out)

    def test_file_entry_fails_when_that_file_is_built(self):
        rc, out = self.run_check('--spdx', self.write('s.json', spdx(BASE + ['kernel/sched/ext.c'])))
        self.assertEqual(rc, 1, out)
        self.assertIn('CVE-2026-43326', out)

    def test_every_named_path_is_checked(self):
        # One compiled file under each path the status file names: each entry fails.
        named = ['kernel/sched/ext.c', 'arch/arm64/kvm/x.c', 'drivers/infiniband/x.c',
                 'net/xdp/x.c', 'fs/erofs/x.c', 'net/smc/x.c', 'net/rose/x.c', 'fs/jfs/x.c']
        rc, out = self.run_check('--spdx', self.write('s.json', spdx(BASE + named)))
        self.assertEqual(rc, 1, out)
        self.assertEqual(out.count('FAIL:'), len(named), out)

    def test_empty_compiled_list_is_not_a_pass(self):
        rc, out = self.run_check('--spdx', self.write('s.json', spdx(BASE, purpose='install')))
        self.assertEqual(rc, 1, out)
        self.assertIn('no compiled sources', out)

    def test_missing_control_file_is_not_a_pass(self):
        rc, out = self.run_check('--spdx', self.write(
            's.json', spdx([f for f in BASE if f != 'kernel/fork.c'])))
        self.assertEqual(rc, 1, out)
        self.assertIn('control file', out)

    def test_not_spdx3_is_refused(self):
        rc, out = self.run_check('--spdx', self.write('s.json', {'spdxVersion': 'SPDX-2.2'}))
        self.assertNotEqual(rc, 0, out)

    def test_not_built_entry_without_path_is_refused(self):
        st = self.write('st.inc',
                        'CVE_STATUS[CVE-2016-7545] = "not-applicable-config: sandbox not installed"\n'
                        'CVE_STATUS[CVE-2099-0001] = "not-applicable-config: driver is not built"\n')
        rc, out = self.run_check('--static', status=st)
        self.assertEqual(rc, 1, out)
        self.assertIn('CVE-2099-0001', out)

    def test_stale_unchecked_exception_is_refused(self):
        st = self.write('st.inc', 'CVE_STATUS[CVE-2023-3397] = "not-applicable-config: JFS (fs/jfs) is not built"\n')
        rc, out = self.run_check('--static', status=st)
        self.assertEqual(rc, 1, out)
        self.assertIn('CVE-2016-7545', out)

    def test_duplicate_status_is_refused(self):
        line = 'CVE_STATUS[CVE-2023-3397] = "not-applicable-config: JFS (fs/jfs) is not built"\n'
        st = self.write('st.inc', line + line +
                        'CVE_STATUS[CVE-2016-7545] = "not-applicable-config: sandbox"\n')
        rc, out = self.run_check('--static', status=st)
        self.assertNotEqual(rc, 0, out)
        self.assertIn('two statuses', out)


if __name__ == '__main__':
    unittest.main()
