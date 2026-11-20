"""check_ima_loadable: the release IMA policy is checked the way the kernel
loads it. evmctl and openssl are replaced here; the real tools were run on
signed, mis-keyed and edited ext4 images when the check was written."""

import importlib.util
import os
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_spec = importlib.util.spec_from_file_location(
    'check_release_no_dev_ima', os.path.join(ROOT, 'scripts', 'check-release-no-dev.py'))
nd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nd)

POLICY, KEY = nd.IMA_POLICY, nd.IMA_KEY


class FakeFs:
    def __init__(self, files, xattrs=None):
        self.files = dict(files)
        self.xa = dict(xattrs or {})

    def read(self, path):
        return self.files.get(path)

    def exists(self, path):
        return path in self.files

    def xattrs(self, path):
        return sorted(self.xa.get(path, {}))

    def extract(self, path, dest):
        if path not in self.files:
            return False
        with open(dest, 'w') as f:
            f.write(self.files[path])
        return True

    def extract_xattr(self, path, name, dest):
        value = self.xa.get(path, {}).get(name)
        if not value:
            return False
        with open(dest, 'wb') as f:
            f.write(value)
        return True


def signed_fs():
    return FakeFs({POLICY: 'measure func=BPRM_CHECK\n', KEY: 'der'},
                  {POLICY: {'security.selinux': b'l', 'security.ima': b'\x03sig'}})


class ImaLoadableTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bundle = os.path.join(self.tmp.name, 'system-trusted-bundle.pem')
        with open(self.bundle, 'w') as f:
            f.write('pem')

    def tearDown(self):
        self.tmp.cleanup()

    def kconfig(self, **over):
        vals = {'CONFIG_IMA_LOAD_X509': 'y',
                'CONFIG_IMA_X509_PATH': '"%s"' % KEY,
                'CONFIG_SYSTEM_TRUSTED_KEYS': '"%s"' % self.bundle}
        vals.update(over)
        path = os.path.join(self.tmp.name, '.config')
        with open(path, 'w') as f:
            for k, v in vals.items():
                if v is not None:
                    f.write('%s=%s\n' % (k, v))
        return path

    def run_check(self, fs, kconfig, evm=None, trust=None):
        with mock.patch.object(nd, 'evm_verify', return_value=evm), \
             mock.patch.object(nd, 'cert_trusted', return_value=trust):
            return nd.check_ima_loadable(fs, kconfig)

    def test_no_policy_nothing_to_check(self):
        self.assertEqual(self.run_check(FakeFs({}), None), ([], False))

    def test_unsigned_left_to_check_rootfs(self):
        fs = FakeFs({POLICY: 'measure func=BPRM_CHECK\n', KEY: 'der'})
        self.assertEqual(self.run_check(fs, self.kconfig()), ([], False))

    def test_signed_without_kernel_config_refused(self):
        p, ok = self.run_check(signed_fs(), None)
        self.assertFalse(ok)
        self.assertEqual(len(p), 1, p)
        self.assertIn('--kernel-config', p[0])

    def test_loadable(self):
        self.assertEqual(self.run_check(signed_fs(), self.kconfig()), ([], True))

    def test_signature_does_not_verify(self):
        p, ok = self.run_check(signed_fs(), self.kconfig(), evm='unknown keyid')
        self.assertFalse(ok)
        self.assertEqual(len(p), 1, p)
        self.assertIn('does not verify', p[0])

    def test_certificate_not_trusted_by_kernel(self):
        p, ok = self.run_check(signed_fs(), self.kconfig(), trust='unable to get local issuer')
        self.assertFalse(ok)
        self.assertEqual(len(p), 1, p)
        self.assertIn('not signed by a key the kernel trusts', p[0])

    def test_kernel_does_not_load_the_key(self):
        p, _ = self.run_check(signed_fs(), self.kconfig(CONFIG_IMA_LOAD_X509=None))
        self.assertTrue(any('CONFIG_IMA_LOAD_X509 is not y' in x for x in p), p)

    def test_kernel_loads_the_key_from_elsewhere(self):
        p, _ = self.run_check(signed_fs(), self.kconfig(CONFIG_IMA_X509_PATH='"/etc/keys/other.der"'))
        self.assertTrue(any('CONFIG_IMA_X509_PATH' in x for x in p), p)

    def test_trusted_keys_unreadable(self):
        p, ok = self.run_check(signed_fs(), self.kconfig(CONFIG_SYSTEM_TRUSTED_KEYS='"/mnt/k/none.pem"'))
        self.assertFalse(ok)
        self.assertTrue(any('is K: mounted' in x for x in p), p)

    def test_signature_not_extractable(self):
        fs = signed_fs()
        fs.xa[POLICY] = {'security.ima': b''}
        fs.xattrs = lambda path: ['security.ima']
        p, ok = self.run_check(fs, self.kconfig())
        self.assertFalse(ok)
        self.assertTrue(any('could not copy' in x for x in p), p)


if __name__ == '__main__':
    unittest.main()
