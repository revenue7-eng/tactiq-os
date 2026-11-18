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
import time
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


def record(files):
    """A kernel CNA record shaped like linux-vulns cve/published/*/CVE-*.json."""
    return {'dataType': 'CVE_RECORD',
            'containers': {'cna': {'affected': [
                {'product': 'Linux', 'programFiles': files},
                {'product': 'Linux', 'programFiles': files}]}}}


# The five 2026 entries, with the programFiles of their linux-vulns records as
# of 40859ff8f (2026-11-16).
RECORDS = {
    'CVE-2026-43326': ['kernel/sched/ext.c', 'kernel/sched/sched.h'],
    'CVE-2026-63941': ['arch/arm64/include/asm/kvm_host.h',
                       'arch/arm64/kvm/hyp/include/hyp/switch.h',
                       'arch/arm64/kvm/nested.c', 'arch/arm64/kvm/sys_regs.c'],
    'CVE-2026-74334': ['drivers/infiniband/core/nldev.c',
                       'drivers/infiniband/core/restrack.c',
                       'drivers/infiniband/core/restrack.h',
                       'drivers/infiniband/core/uverbs_cmd.c', 'include/rdma/ib_verbs.h'],
    'CVE-2026-74558': ['Documentation/networking/af_xdp.rst', 'include/net/xsk_buff_pool.h',
                       'net/xdp/xsk.c', 'net/xdp/xsk_buff_pool.c', 'net/xdp/xsk_queue.h'],
    'CVE-2026-80899': ['Documentation/filesystems/erofs.rst', 'fs/erofs/Kconfig',
                       'fs/erofs/Makefile', 'fs/erofs/data.c', 'fs/erofs/fscache.c',
                       'fs/erofs/inode.c', 'fs/erofs/internal.h', 'fs/erofs/ishare.c',
                       'fs/erofs/super.c', 'fs/erofs/zdata.c'],
}

# Headers from those records that the linux-yocto 6.18.54 build of
# 2026-11-16 compiles.
SHARED_HEADERS = ['kernel/sched/sched.h', 'arch/arm64/include/asm/kvm_host.h',
                  'include/rdma/ib_verbs.h']


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

    # upstream records (--vulns)

    def vulns(self, records=RECORDS, rejected=()):
        root = os.path.join(self.tmp.name, 'vulns')
        for cve, files in records.items():
            state = 'rejected' if cve in rejected else 'published'
            d = os.path.join(root, 'cve', state, cve.split('-')[1])
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, cve + '.json'), 'w') as f:
                json.dump(record(files), f)
        os.makedirs(os.path.join(root, 'cve', 'published'), exist_ok=True)
        return root

    def test_upstream_records_as_read_pass(self):
        rc, out = self.run_check('--static', '--vulns', self.vulns())
        self.assertEqual(rc, 0, out)
        self.assertIn('5 of 8 entries checked', out)
        self.assertIn('no linux-vulns record for CVE-2023-3397', out)

    def test_compiled_shared_header_is_a_note_not_a_failure(self):
        s = self.write('s.json', spdx(BASE + SHARED_HEADERS))
        rc, out = self.run_check('--spdx', s, '--vulns', self.vulns())
        self.assertEqual(rc, 0, out)
        self.assertIn('note: CVE-2026-43326: the record also names header(s)', out)

    def test_upstream_rejected_cve_fails(self):
        rc, out = self.run_check('--static', '--vulns', self.vulns(rejected=('CVE-2026-80899',)))
        self.assertEqual(rc, 1, out)
        self.assertIn('CVE-2026-80899: upstream has rejected', out)

    def test_upstream_widened_to_code_outside_named_path_fails(self):
        # Upstream reassesses: the flaw is also in fs/iomap, which we build.
        recs = dict(RECORDS)
        recs['CVE-2026-80899'] = RECORDS['CVE-2026-80899'] + ['fs/iomap/buffered-io.c']
        rc, out = self.run_check('--static', '--vulns', self.vulns(recs))
        self.assertEqual(rc, 1, out)
        self.assertIn('outside fs/erofs: fs/iomap/buffered-io.c', out)

    def test_record_code_compiled_fails(self):
        recs = dict(RECORDS)
        recs['CVE-2026-43326'] = ['kernel/sched/ext.c', 'kernel/sched/core.c']
        s = self.write('s.json', spdx(BASE))
        rc, out = self.run_check('--spdx', s, '--vulns', self.vulns(recs))
        self.assertEqual(rc, 1, out)
        self.assertIn('code the upstream record names is compiled: kernel/sched/core.c', out)

    def test_record_without_code_file_fails(self):
        recs = dict(RECORDS)
        recs['CVE-2026-74558'] = ['include/net/xsk_buff_pool.h']
        rc, out = self.run_check('--static', '--vulns', self.vulns(recs))
        self.assertEqual(rc, 1, out)
        self.assertIn('CVE-2026-74558: the upstream record names no code file', out)

    def test_not_a_vulns_checkout_fails(self):
        rc, out = self.run_check('--static', '--vulns', self.tmp.name)
        self.assertEqual(rc, 1, out)
        self.assertIn('not a linux-vulns checkout', out)

    # age of the checkout (--vulns-max-age)

    def git_vulns(self, days_old):
        """The records above as a git checkout whose only commit is days_old days old."""
        root = self.vulns()
        when = f'@{int(time.time()) - days_old * 86400} +0000'
        env = dict(os.environ, GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when,
                   GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@example.org',
                   GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@example.org')
        for cmd in (['init', '-q'], ['add', '-A'], ['commit', '-q', '-m', 'records']):
            subprocess.run(['git', '-C', root, *cmd], env=env, check=True)
        return root

    def test_fresh_checkout_passes_and_names_its_revision(self):
        rc, out = self.run_check('--static', '--vulns', self.git_vulns(1), '--vulns-max-age', '7')
        self.assertEqual(rc, 0, out)
        self.assertRegex(out, r'linux-vulns: [0-9a-f]{40} \(\d{4}-\d{2}-\d{2}\)')

    def test_old_checkout_fails(self):
        rc, out = self.run_check('--static', '--vulns', self.git_vulns(30), '--vulns-max-age', '7')
        self.assertEqual(rc, 1, out)
        self.assertIn('committed 30 days ago; the limit is 7', out)

    def test_checkout_that_is_not_git_fails_the_age_check(self):
        rc, out = self.run_check('--static', '--vulns', self.vulns(), '--vulns-max-age', '7')
        self.assertEqual(rc, 1, out)
        self.assertIn('is not a git checkout; its age cannot be checked', out)

    def test_age_limit_without_records_is_refused(self):
        rc, out = self.run_check('--static', '--vulns-max-age', '7')
        self.assertEqual(rc, 2, out)
        self.assertIn('--vulns-max-age needs --vulns', out)


if __name__ == '__main__':
    unittest.main()
