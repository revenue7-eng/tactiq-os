#!/usr/bin/env python3
"""check-kernel-keyrings.py: the kernel's trusted keyrings are what the
release says they are.

Reads the .config of a built kernel and the trusted keys file it names, and
checks:

  structure   CONFIG_SECONDARY_TRUSTED_KEYRING is off (no key is added at
              run time), CONFIG_INTEGRITY_TRUSTED_KEYRING is on (.ima takes
              only certificates a builtin key signed), there is no
              CONFIG_SYSTEM_EXTRA_CERTIFICATE slot, and
              CONFIG_SYSTEM_TRUSTED_KEYS holds exactly one certificate: a
              self-signed CA with pathlen 0, the IMA CA (gen-pki.sh ima);
  pin         with --ima-ca-fp, that certificate has this SHA-256
              fingerprint.

The module signing key reaches the builtin keyring through
CONFIG_MODULE_SIG_KEY, not this file, and is pinned by mk-release.sh on the
modules themselves.

Exit status: 0 when everything holds; otherwise the sum of 1 (structure) and
2 (pin). Kept apart so that mk-release.sh can let a mechanics test through a
pin mismatch (ALLOW_UNPINNED_KEYS) but never a structure problem. Other
values are errors of the script itself.

Usage:
  check-kernel-keyrings.py --kernel-config <kernel build>/.config [--ima-ca-fp AA:BB:...]
"""

import argparse
import re
import subprocess
import sys

EXIT_STRUCTURE = 1
EXIT_PIN = 2

BEGIN = '-----BEGIN CERTIFICATE-----'


def kernel_config_values(path):
    """CONFIG_* values of a kernel .config, quotes stripped; 'is not set' lines are absent."""
    vals = {}
    with open(path) as f:
        for line in f:
            m = re.match(r'^(CONFIG_[A-Za-z0-9_]+)=(.*)$', line.strip())
            if m:
                vals[m.group(1)] = m.group(2).strip('"')
    return vals


def openssl(*args, data=None):
    return subprocess.run(['openssl'] + list(args), input=data,
                          capture_output=True, text=True)


def check(kernel_config, ima_ca_fp=None):
    """(structure problems, pin problems, fingerprint or None)."""
    cfg = kernel_config_values(kernel_config)
    structure, pin = [], []
    if cfg.get('CONFIG_SECONDARY_TRUSTED_KEYRING') == 'y':
        structure.append('CONFIG_SECONDARY_TRUSTED_KEYRING=y: root can add a key signed '
                         'by a builtin key at run time')
    if cfg.get('CONFIG_INTEGRITY_TRUSTED_KEYRING') != 'y':
        structure.append('CONFIG_INTEGRITY_TRUSTED_KEYRING is not y: .ima would take '
                         'any certificate')
    if cfg.get('CONFIG_SYSTEM_EXTRA_CERTIFICATE') == 'y':
        structure.append('CONFIG_SYSTEM_EXTRA_CERTIFICATE=y: the kernel image has room '
                         'for a certificate inserted after the build')
    bundle = cfg.get('CONFIG_SYSTEM_TRUSTED_KEYS', '')
    if not bundle:
        return structure + ['CONFIG_SYSTEM_TRUSTED_KEYS is empty: no IMA CA in the '
                            'builtin keyring, .ima cannot take x509_ima.der'], pin, None
    try:
        with open(bundle) as f:
            text = f.read()
    except OSError as e:
        return structure + ['the trusted keys %s (CONFIG_SYSTEM_TRUSTED_KEYS) are not '
                            'readable here (is K: mounted?): %s' % (bundle, e)], pin, None
    n = text.count(BEGIN)
    if n != 1:
        return structure + ['%s holds %d certificates; the builtin keyring takes the IMA '
                            'CA alone' % (bundle, n)], pin, None
    r = openssl('x509', '-noout', '-ext', 'basicConstraints', data=text)
    bc = ' '.join(r.stdout.split()) if r.returncode == 0 else ''
    if 'CA:TRUE' not in bc or 'pathlen:0' not in bc:
        structure.append('%s is not a CA with pathlen 0 (basicConstraints: %s)'
                         % (bundle, bc or 'none'))
    r = openssl('verify', '-CAfile', bundle, bundle)
    if r.returncode != 0 or not r.stdout.strip().endswith(': OK'):
        structure.append('%s is not self-signed: the IMA CA is a root of its own (%s)'
                         % (bundle, ' '.join((r.stderr + r.stdout).split())))
    r = openssl('x509', '-noout', '-fingerprint', '-sha256', data=text)
    fp = r.stdout.strip().split('=', 1)[-1] if r.returncode == 0 else None
    if ima_ca_fp is not None and (fp or '').upper() != ima_ca_fp.upper():
        pin.append('the IMA CA in %s has fingerprint %s, the pinned release IMA CA %s'
                   % (bundle, fp or 'unreadable', ima_ca_fp or '(no pin set)'))
    return structure, pin, fp


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--kernel-config', required=True)
    ap.add_argument('--ima-ca-fp')
    a = ap.parse_args(argv)
    try:
        structure, pin, fp = check(a.kernel_config, a.ima_ca_fp)
    except OSError as e:
        print('check-kernel-keyrings: cannot read %s: %s' % (a.kernel_config, e), file=sys.stderr)
        return 8
    for p in structure:
        print('check-kernel-keyrings: %s' % p, file=sys.stderr)
    for p in pin:
        print('check-kernel-keyrings: %s' % p, file=sys.stderr)
    if structure or pin:
        return (EXIT_STRUCTURE if structure else 0) | (EXIT_PIN if pin else 0)
    print('    kernel keyrings: no secondary keyring; builtin holds the IMA CA %s and '
          'the module signing key' % fp)
    return 0


if __name__ == '__main__':
    sys.exit(main())
