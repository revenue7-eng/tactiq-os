#!/usr/bin/env python3
"""Tests for scripts/check-kernel-keyrings.py.

Certificates are made here with openssl: an IMA CA as gen-pki.sh ima makes
it, and the shapes the check must refuse. Each refusal is checked by its
own test, so that a check which stopped working fails one.
"""

import importlib.util
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
spec = importlib.util.spec_from_file_location(
    'check_kernel_keyrings', os.path.join(ROOT, 'scripts', 'check-kernel-keyrings.py'))
kk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kk)

GOOD_CONFIG = (
    'CONFIG_INTEGRITY_TRUSTED_KEYRING=y\n'
    '# CONFIG_SECONDARY_TRUSTED_KEYRING is not set\n'
    '# CONFIG_SYSTEM_EXTRA_CERTIFICATE is not set\n'
    'CONFIG_SYSTEM_TRUSTED_KEYS="%s"\n'
)


def run(*args):
    subprocess.run(list(args), check=True, capture_output=True)


class KernelKeyrings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        d = cls.tmp.name
        cls.d = d

        def ca(name, ext):
            cnf = os.path.join(d, name + '.cnf')
            with open(cnf, 'w') as f:
                f.write('[req]\ndistinguished_name = dn\n[dn]\n[ext]\n' + ext)
            run('openssl', 'req', '-x509', '-new', '-newkey', 'rsa:2048', '-nodes',
                '-keyout', os.path.join(d, name + '.key'), '-subj', '/CN=' + name,
                '-days', '30', '-config', cnf, '-extensions', 'ext',
                '-out', os.path.join(d, name + '.pem'))
            return os.path.join(d, name + '.pem')

        cls.ima_ca = ca('imaca', 'basicConstraints = critical, CA:TRUE, pathlen:0\n'
                                 'keyUsage = critical, keyCertSign, cRLSign\n')
        cls.root_ca = ca('rootca', 'basicConstraints = critical, CA:TRUE, pathlen:1\n'
                                   'keyUsage = critical, keyCertSign, cRLSign\n')
        cls.leaf_self = ca('leaf', 'basicConstraints = critical, CA:FALSE\n'
                                   'keyUsage = critical, digitalSignature\n')
        # A CA with pathlen 0 issued by rootca: not self-signed.
        csr = os.path.join(d, 'sub.csr')
        run('openssl', 'req', '-new', '-newkey', 'rsa:2048', '-nodes',
            '-keyout', os.path.join(d, 'sub.key'), '-subj', '/CN=sub', '-out', csr)
        ext = os.path.join(d, 'sub.ext')
        with open(ext, 'w') as f:
            f.write('basicConstraints = critical, CA:TRUE, pathlen:0\n')
        cls.sub_ca = os.path.join(d, 'sub.pem')
        run('openssl', 'x509', '-req', '-in', csr, '-CA', cls.root_ca,
            '-CAkey', os.path.join(d, 'rootca.key'), '-CAcreateserial',
            '-days', '30', '-extfile', ext, '-out', cls.sub_ca)
        r = subprocess.run(['openssl', 'x509', '-in', cls.ima_ca, '-noout',
                            '-fingerprint', '-sha256'], capture_output=True, text=True)
        cls.fp = r.stdout.strip().split('=', 1)[1]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def config(self, text):
        path = os.path.join(self.d, 'config-%d' % id(text))
        with open(path, 'w') as f:
            f.write(text)
        return path

    def bundle(self, *certs):
        path = os.path.join(self.d, 'bundle-%d.pem' % abs(hash(certs)))
        with open(path, 'w') as f:
            for c in certs:
                with open(c) as g:
                    f.write(g.read())
        return path

    def test_ima_ca_alone_passes(self):
        cfg = self.config(GOOD_CONFIG % self.bundle(self.ima_ca))
        self.assertEqual(kk.check(cfg, self.fp)[:2], ([], []))
        self.assertEqual(kk.main(['--kernel-config', cfg, '--ima-ca-fp', self.fp]), 0)

    def test_secondary_keyring_refused(self):
        cfg = self.config((GOOD_CONFIG % self.bundle(self.ima_ca)).replace(
            '# CONFIG_SECONDARY_TRUSTED_KEYRING is not set', 'CONFIG_SECONDARY_TRUSTED_KEYRING=y'))
        structure, pin, _ = kk.check(cfg, self.fp)
        self.assertTrue(any('SECONDARY' in p for p in structure), structure)
        self.assertEqual(kk.main(['--kernel-config', cfg, '--ima-ca-fp', self.fp]), 1)

    def test_integrity_trusted_keyring_off_refused(self):
        cfg = self.config((GOOD_CONFIG % self.bundle(self.ima_ca)).replace(
            'CONFIG_INTEGRITY_TRUSTED_KEYRING=y', '# CONFIG_INTEGRITY_TRUSTED_KEYRING is not set'))
        self.assertTrue(any('INTEGRITY_TRUSTED' in p for p in kk.check(cfg)[0]))

    def test_extra_certificate_slot_refused(self):
        cfg = self.config((GOOD_CONFIG % self.bundle(self.ima_ca)).replace(
            '# CONFIG_SYSTEM_EXTRA_CERTIFICATE is not set', 'CONFIG_SYSTEM_EXTRA_CERTIFICATE=y'))
        self.assertTrue(any('EXTRA_CERTIFICATE' in p for p in kk.check(cfg)[0]))

    def test_old_three_certificate_bundle_refused(self):
        # root + signing CA + leaf, as the bundle was before the IMA CA.
        cfg = self.config(GOOD_CONFIG % self.bundle(self.root_ca, self.sub_ca, self.leaf_self))
        structure, _, _ = kk.check(cfg, self.fp)
        self.assertTrue(any('holds 3 certificates' in p for p in structure), structure)

    def test_leaf_alone_refused(self):
        cfg = self.config(GOOD_CONFIG % self.bundle(self.leaf_self))
        self.assertTrue(any('not a CA' in p for p in kk.check(cfg)[0]))

    def test_ca_with_longer_path_refused(self):
        cfg = self.config(GOOD_CONFIG % self.bundle(self.root_ca))
        self.assertTrue(any('pathlen 0' in p for p in kk.check(cfg)[0]))

    def test_issued_ca_refused(self):
        cfg = self.config(GOOD_CONFIG % self.bundle(self.sub_ca))
        self.assertTrue(any('not self-signed' in p for p in kk.check(cfg)[0]))

    def test_missing_bundle_refused(self):
        cfg = self.config(GOOD_CONFIG % os.path.join(self.d, 'absent.pem'))
        self.assertTrue(any('not readable' in p for p in kk.check(cfg)[0]))

    def test_empty_trusted_keys_refused(self):
        cfg = self.config(GOOD_CONFIG % '')
        self.assertTrue(any('empty' in p for p in kk.check(cfg)[0]))

    def test_pin_mismatch_is_its_own_bit(self):
        cfg = self.config(GOOD_CONFIG % self.bundle(self.ima_ca))
        other = 'AA:' * 31 + 'AA'
        structure, pin, _ = kk.check(cfg, other)
        self.assertEqual(structure, [])
        self.assertEqual(len(pin), 1)
        self.assertEqual(kk.main(['--kernel-config', cfg, '--ima-ca-fp', other]), 2)

    def test_empty_pin_refused(self):
        # mk-release passes the pin even before the ceremony set it.
        cfg = self.config(GOOD_CONFIG % self.bundle(self.ima_ca))
        self.assertEqual(kk.main(['--kernel-config', cfg, '--ima-ca-fp', '']), 2)

    def test_structure_and_pin_add_up(self):
        cfg = self.config((GOOD_CONFIG % self.bundle(self.ima_ca)).replace(
            '# CONFIG_SECONDARY_TRUSTED_KEYRING is not set', 'CONFIG_SECONDARY_TRUSTED_KEYRING=y'))
        self.assertEqual(kk.main(['--kernel-config', cfg, '--ima-ca-fp', '']), 3)

    def test_dev_tree_passes_structure(self):
        # The development pki/dev bundle, as committed, is the IMA CA alone.
        b = os.path.join(ROOT, 'pki', 'dev', 'system-trusted-bundle.pem')
        cfg = self.config(GOOD_CONFIG % os.path.abspath(b))
        self.assertEqual(kk.check(cfg)[0], [])


if __name__ == '__main__':
    unittest.main()
