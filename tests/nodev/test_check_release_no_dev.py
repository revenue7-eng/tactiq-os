#!/usr/bin/env python3
"""Tests for scripts/check-release-no-dev.py.

The dev recipe parsed is the real one in the tree. The package check runs on
the manifest of the published v2.1.0-rc14 release, kept here as
manifest-v2.1.0-rc14.txt. Rootfs checks run on an in-memory file tree, so the
tests need no debugfs.
"""

import importlib.util
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
spec = importlib.util.spec_from_file_location(
    'check_release_no_dev', os.path.join(ROOT, 'scripts', 'check-release-no-dev.py'))
nd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nd)

DEV_RECIPE = os.path.join(ROOT, 'recipes-core', 'images', 'tactiq-image-dev.bb')
RC14_MANIFEST = os.path.join(HERE, 'manifest-v2.1.0-rc14.txt')


def text(path):
    with open(path) as f:
        return f.read()

CLEAN = {
    '/etc/shadow': 'root:!:19000:0:99999:7:::\n',
    '/etc/passwd': 'root:x:0:0:root:/root:/bin/sh\n',
    '/etc/pam.d/common-auth': 'auth\t[success=1 default=ignore]\tpam_unix.so nullok_secure\n',
    '/etc/audit/auditd.conf': 'log_file = /var/log/audit/audit.log\n',
}


class FakeFs:
    def __init__(self, files):
        self.files = dict(files)

    def read(self, path):
        return self.files.get(path)

    def listdir(self, path):
        pre = path.rstrip('/') + '/'
        return sorted(p[len(pre):] for p in self.files
                      if p.startswith(pre) and '/' not in p[len(pre):])


class NoDevTest(unittest.TestCase):

    def setUp(self):
        self.dev = nd.parse_dev_recipe(DEV_RECIPE)
        self.checks, self.unknown = nd.required_checks(self.dev)

    def rootfs(self, changes=None):
        files = dict(CLEAN)
        for path, v in (changes or {}).items():
            if v is None:
                files.pop(path, None)
            else:
                files[path] = v
        return nd.check_rootfs(FakeFs(files), self.checks)

    def test_dev_recipe_fully_covered(self):
        self.assertEqual(self.unknown, [])
        for p in ('openssh-sshd', 'jq', 'tactiq-status', 'libtss2-tcti-mssim', 'curl'):
            self.assertIn(p, self.dev['packages'])
        self.assertEqual(self.checks, {'root-locked', 'pam-nullok', 'postinst-logging',
                                       'no-ima-policy', 'audit-log'})

    def test_unknown_addition_is_reported(self):
        with tempfile.NamedTemporaryFile('w', suffix='.bb', delete=False) as f:
            f.write(text(DEV_RECIPE) + '\nEXTRA_IMAGE_FEATURES:append = " tools-debug"\n')
        try:
            _, unknown = nd.required_checks(nd.parse_dev_recipe(f.name))
        finally:
            os.unlink(f.name)
        self.assertEqual(unknown, ['image feature tools-debug'])

    def test_rc14_manifest_has_no_dev_packages(self):
        self.assertEqual(nd.check_manifest(RC14_MANIFEST, self.dev['packages']), [])

    def test_dev_package_in_manifest(self):
        with tempfile.NamedTemporaryFile('w', delete=False) as f:
            f.write(text(RC14_MANIFEST) + 'openssh-sshd cortexa76-cortexa55 9.9p2-r0\n')
        try:
            problems = nd.check_manifest(f.name, self.dev['packages'])
        finally:
            os.unlink(f.name)
        self.assertEqual(problems, ['development package in the release image: openssh-sshd'])

    def test_clean_rootfs(self):
        self.assertEqual(self.rootfs(), [])

    def refused(self, changes, needle):
        p = self.rootfs(changes)
        self.assertTrue(any(needle in x for x in p), 'no problem mentions %r: %s' % (needle, p))

    def test_empty_root_password(self):
        self.refused({'/etc/shadow': 'root::19000:0:99999:7:::\n'}, 'root is not locked')

    def test_root_with_hash(self):
        self.refused({'/etc/shadow': 'root:$6$abc$def:19000:0:99999:7:::\n'}, 'root is not locked')

    def test_empty_passwd_field(self):
        self.refused({'/etc/passwd': 'root::0:0:root:/root:/bin/sh\n'}, 'empty password field')

    def test_pam_nullok(self):
        self.refused({'/etc/pam.d/common-auth': 'auth required pam_unix.so nullok\n'},
                     'accepts empty passwords')

    def test_pam_nullok_secure_is_fine(self):
        self.assertEqual(self.rootfs({'/etc/pam.d/login': 'auth required pam_unix.so nullok_secure\n'}), [])

    def test_postinst_logging(self):
        self.refused({'/etc/default/postinst': 'POSTINST_LOGGING=1\nLOGFILE=/var/log/x\n'},
                     'postinst logging')

    def test_ima_policy(self):
        self.refused({'/etc/ima/ima-policy': 'measure func=BPRM_CHECK\n'}, 'ima-policy')

    def test_dev_audit_log(self):
        self.refused({'/etc/audit/auditd.conf':
                      'log_file = /data/tactiq/measurement/audit/audit.log\n'},
                     'measurement tree')


if __name__ == '__main__':
    unittest.main(verbosity=2)
