#!/usr/bin/env python3
"""check-release-no-dev.py: nothing the development profile adds is in a
release image.

The development profile is declared in one place,
recipes-core/images/tactiq-image-dev.bb. This script reads that recipe and
checks the release artefacts against everything it adds:

  packages      every package the dev recipe installs is absent from the
                release manifest, except those production pulls in for a
                reason of its own (PRODUCTION_ALSO below, with the reason);
  features      each debug image feature, image class and image hook of the
                dev recipe maps to a check on the release rootfs, read with
                debugfs: root is locked, PAM has no plain nullok, there is no
                postinst logging, no IMA appraise rule (the release policy
                measures only, tactiq-ima-measure-policy).

Two modes:

  --static      read the dev recipe only and fail if it adds anything this
                script has no check for (CI: a new dev addition cannot land
                without a release check, or an explicit "build only" entry);
  default       also read --manifest and --rootfs and check the release.

Usage:
  check-release-no-dev.py --dev-recipe recipes-core/images/tactiq-image-dev.bb --static
  check-release-no-dev.py --dev-recipe recipes-core/images/tactiq-image-dev.bb \\
      --manifest <image>.manifest --rootfs <image>.ext4 \\
      --kernel-config <kernel build>/.config

A release rootfs that carries an IMA policy is also checked the way the
kernel will load it: the kernel loads /etc/keys/x509_ima.der
(CONFIG_IMA_LOAD_X509, CONFIG_IMA_X509_PATH), takes it into .ima only if a
key in CONFIG_SYSTEM_TRUSTED_KEYS signed it, and accepts the policy only if
its security.ima verifies with that certificate. --kernel-config is the
.config of the release kernel; the trusted keys file it names must be
readable (K: mounted).

Exit status 0 when everything holds, 1 otherwise. Reads files and runs
debugfs read-only; changes nothing. The policy, its signature and the
certificate are copied out to a temporary directory for evmctl and openssl.
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile

IMA_POLICY = '/etc/ima/ima-policy'
IMA_KEY = '/etc/keys/x509_ima.der'

# Packages the dev recipe installs that production carries anyway.
PRODUCTION_ALSO = {
    'audit': 'RDEPENDS of dbus-1, shadow-base, libsemanage2 and '
             'policycoreutils-setfiles (tactiq-image.bb); the library only, '
             'the daemon is package auditd',
    'tpm2-tools': 'RDEPENDS of tactiq-agent, which reaches the TPM through it; '
                  'leaves production when the agent moves to tss-esapi',
    'ima-evm-keys': 'tactiq-image.bb: the IMA signer certificate the kernel '
                    'verifies the release IMA policy against (IMA_EVM_X509, '
                    'a release key, not the development one: keygate)',
}

# Image features of the dev recipe -> rootfs check. Package-level features
# (an SSH server) are covered by the package check.
FEATURE_CHECKS = {
    'ssh-server-openssh': 'packages',
    'allow-empty-password': 'pam-nullok',
    'allow-root-login': 'root-locked',
    'empty-root-password': 'root-locked',
    'post-install-logging': 'postinst-logging',
}
CLASS_CHECKS = {'ima-evm-rootfs': 'no-appraise-policy'}
INHERIT_CHECKS = {'create-spdx': None}   # None: build side only, nothing in the rootfs
VARIABLE_CHECKS = {'EXTRA_USERS_PARAMS': 'root-locked'}
HOOK_CHECKS = {
    'tactiq_ima_policy_mode': 'no-appraise-policy',
}


def code_lines(path):
    """Recipe lines with comments removed and backslash continuations joined."""
    out, cur = [], ''
    with open(path) as f:
        for raw in f:
            line = raw.rstrip('\n')
            if not cur and line.lstrip().startswith('#'):
                continue
            if line.endswith('\\'):
                cur += line[:-1] + ' '
                continue
            out.append(cur + line)
            cur = ''
    if cur:
        out.append(cur)
    return out


def assigned(lines, name_re, ops=r'(?:\+=|=|:append\s*=)'):
    """Words of every assignment to a variable matching name_re."""
    words = []
    pat = re.compile(r'^\s*(%s)\s*%s\s*"([^"]*)"' % (name_re, ops))
    for line in lines:
        m = pat.match(line)
        if m:
            words += m.group(2).split()
    return words


def parse_dev_recipe(path):
    lines = code_lines(path)
    debug = assigned(lines, r'TACTIQ_DEBUG_FEATURES', r'=')
    features = assigned(lines, r'IMAGE_FEATURES', r'\+=')
    for w in assigned(lines, r'EXTRA_IMAGE_FEATURES', r'(?::append\s*=|\+=|=)'):
        features += debug if w == '${TACTIQ_DEBUG_FEATURES}' else [w]
    hooks = assigned(lines, r'ROOTFS_POSTPROCESS_COMMAND', r'(?:\+=|:append\s*=)')
    hooks += assigned(lines, r'do_image\[postfuncs\]', r'\+=')
    variables = [v for v in VARIABLE_CHECKS
                 if any(re.match(r'^\s*%s\s*=' % v, l) for l in lines)]
    return {
        'packages': assigned(lines, r'IMAGE_INSTALL', r'(?::append\s*=|\+=)'),
        'features': features,
        'classes': assigned(lines, r'IMAGE_CLASSES', r'\+='),
        'inherits': assigned(lines, r'INHERIT', r'\+='),
        'hooks': hooks,
        'variables': variables,
    }


def required_checks(dev):
    """Rootfs checks the dev recipe calls for, and additions with no check."""
    checks, unknown = set(), []
    for kind, table, items in (('image feature', FEATURE_CHECKS, dev['features']),
                               ('image class', CLASS_CHECKS, dev['classes']),
                               ('INHERIT', INHERIT_CHECKS, dev['inherits']),
                               ('image hook', HOOK_CHECKS, dev['hooks']),
                               ('variable', VARIABLE_CHECKS, dev['variables'])):
        for item in items:
            if item not in table:
                unknown.append('%s %s' % (kind, item))
            elif table[item] not in (None, 'packages'):
                checks.add(table[item])
    return checks, unknown


class Rootfs:
    """Read-only access to an ext4 image through debugfs."""

    def __init__(self, image):
        self.image = image

    def _run(self, request):
        r = subprocess.run(['debugfs', '-R', request, self.image],
                           capture_output=True, text=True,
                           env={'DEBUGFS_PAGER': '__none__', 'PATH': '/usr/sbin:/sbin:/usr/bin:/bin'})
        return r.stdout

    def read(self, path):
        """File contents, or None when the file does not exist."""
        stat = self._run('stat %s' % path)
        if 'Inode:' not in stat:
            return None
        return self._run('cat %s' % path)

    def exists(self, path):
        return 'Inode:' in self._run('stat %s' % path)

    def xattrs(self, path):
        """Names of the extended attributes of path (empty if none or absent)."""
        out = self._run('ea_list %s' % path)
        return [l.split()[0] for l in out.splitlines()
                if l.startswith('  ') and l.split()]

    def extract(self, path, dest):
        """Copy path out of the image to dest; True when dest was written."""
        self._run('dump %s %s' % (path, dest))
        return os.path.isfile(dest)

    def extract_xattr(self, path, name, dest):
        """Write the raw value of xattr name of path to dest; True when non-empty."""
        self._run('ea_get -f %s %s %s' % (dest, path, name))
        return os.path.isfile(dest) and os.path.getsize(dest) > 0

    def listdir(self, path):
        out = self._run('ls -p %s' % path)
        names = []
        for line in out.splitlines():
            parts = line.strip('/').split('/')
            if len(parts) >= 5 and parts[4] not in ('.', '..'):
                names.append(parts[4])
        return names


def check_rootfs(fs, checks):
    problems = []
    if 'root-locked' in checks:
        shadow = fs.read('/etc/shadow') or ''
        root = [l for l in shadow.splitlines() if l.startswith('root:')]
        pw = root[0].split(':')[1] if root and len(root[0].split(':')) > 1 else None
        if pw is None:
            problems.append('/etc/shadow has no root entry')
        elif not pw or pw[0] not in '!*':
            problems.append('root is not locked in /etc/shadow (password field %r)'
                            % (pw[:3] + '...' if pw else pw))
        passwd = fs.read('/etc/passwd') or ''
        for l in passwd.splitlines():
            if l.startswith('root:') and l.split(':')[1] == '':
                problems.append('root has an empty password field in /etc/passwd')
    if 'pam-nullok' in checks:
        for name in fs.listdir('/etc/pam.d'):
            text = fs.read('/etc/pam.d/%s' % name) or ''
            for l in text.splitlines():
                if not l.lstrip().startswith('#') and re.search(r'\bnullok\b(?!_)', l):
                    problems.append('/etc/pam.d/%s accepts empty passwords: %s'
                                    % (name, l.strip()))
    if 'postinst-logging' in checks:
        text = fs.read('/etc/default/postinst')
        if text is not None and 'POSTINST_LOGGING=1' in text:
            problems.append('/etc/default/postinst enables postinst logging')
    # Not keyed to the dev recipe: a release that carries an IMA policy must
    # be able to load it. The kernel accepts only a policy file with an IMA
    # signature that verifies against the .ima keyring, loaded from
    # /etc/keys/x509_ima.der, and systemd freezes the boot when the load
    # fails (20.11.2026: unsigned policy, no /etc/keys, froze at 2.3 s).
    if fs.read('/etc/ima/ima-policy') is not None:
        if 'security.ima' not in fs.xattrs('/etc/ima/ima-policy'):
            problems.append('/etc/ima/ima-policy has no IMA signature (security.ima): '
                            'the kernel refuses the policy and the boot freezes')
        if not fs.exists('/etc/keys/x509_ima.der'):
            problems.append('/etc/keys/x509_ima.der is missing: the kernel has no key '
                            'to verify the IMA policy with and the boot freezes')
    if 'no-appraise-policy' in checks:
        # A release carries a policy that measures (tactiq-ima-measure-policy).
        # What the development profile adds is appraisal, keyed to the in-tree
        # IMA key: an appraise rule in a release refuses its unsigned files, or
        # accepts files signed with a public key.
        text = fs.read('/etc/ima/ima-policy')
        for l in (text or '').splitlines():
            if l.split()[:1] == ['appraise']:
                problems.append('/etc/ima/ima-policy has an appraise rule '
                                '(development IMA policy): %s' % l.strip())
    return problems


def kernel_config_values(path):
    """CONFIG_* values of a kernel .config, quotes stripped."""
    vals = {}
    with open(path) as f:
        for line in f:
            m = re.match(r'^(CONFIG_[A-Za-z0-9_]+)=(.*)$', line.strip())
            if m:
                vals[m.group(1)] = m.group(2).strip('"')
    return vals


def evm_verify(path, cert):
    """None when the IMA signature in path.sig verifies with cert, else why not."""
    r = subprocess.run(['evmctl', 'ima_verify', '--sigfile', '--key', cert, path],
                       capture_output=True, text=True)
    if r.returncode == 0:
        return None
    msg = (r.stderr + r.stdout).strip().splitlines()
    return msg[-1] if msg else 'evmctl exit %d' % r.returncode


def cert_trusted(cert_der, bundle):
    """None when cert_der chains to the certificates in bundle, else why not."""
    with tempfile.TemporaryDirectory() as tmp:
        pem = os.path.join(tmp, 'cert.pem')
        r = subprocess.run(['openssl', 'x509', '-inform', 'der', '-in', cert_der, '-out', pem],
                           capture_output=True, text=True)
        if r.returncode:
            return 'not a DER certificate: %s' % r.stderr.strip()
        r = subprocess.run(['openssl', 'verify', '-CAfile', bundle, pem],
                           capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip().endswith(': OK'):
            return None
        return ' '.join((r.stderr + r.stdout).split())


def check_ima_loadable(fs, kernel_config):
    """Problems with loading the IMA policy as the kernel will, and whether it
    was verified. Does nothing when there is no policy, or when check_rootfs
    already reports the signature or the certificate as missing."""
    if fs.read(IMA_POLICY) is None:
        return [], False
    if 'security.ima' not in fs.xattrs(IMA_POLICY) or not fs.exists(IMA_KEY):
        return [], False
    if not kernel_config:
        return ['%s is signed but not checked against the kernel: pass --kernel-config '
                '(the .config of the release kernel)' % IMA_POLICY], False
    try:
        cfg = kernel_config_values(kernel_config)
    except OSError as e:
        return ['cannot read the kernel config %s: %s' % (kernel_config, e)], False
    problems = []
    if cfg.get('CONFIG_IMA_LOAD_X509') != 'y':
        problems.append('the kernel does not load %s (CONFIG_IMA_LOAD_X509 is not y): '
                        'nothing verifies the IMA policy and the boot freezes' % IMA_KEY)
    if cfg.get('CONFIG_IMA_X509_PATH') != IMA_KEY:
        problems.append('the kernel loads its IMA key from %r (CONFIG_IMA_X509_PATH), '
                        'the image has it at %s' % (cfg.get('CONFIG_IMA_X509_PATH'), IMA_KEY))
    bundle = cfg.get('CONFIG_SYSTEM_TRUSTED_KEYS', '')
    if not bundle or not os.path.isfile(bundle):
        problems.append('the kernel trusted keys %r (CONFIG_SYSTEM_TRUSTED_KEYS) are not '
                        'readable here (is K: mounted?)' % bundle)
        bundle = None
    with tempfile.TemporaryDirectory() as tmp:
        cert = os.path.join(tmp, 'x509_ima.der')
        policy = os.path.join(tmp, 'ima-policy')
        if not (fs.extract(IMA_KEY, cert) and fs.extract(IMA_POLICY, policy)
                and fs.extract_xattr(IMA_POLICY, 'security.ima', policy + '.sig')):
            return problems + ['could not copy %s, %s and its security.ima out of the image'
                               % (IMA_KEY, IMA_POLICY)], False
        why = evm_verify(policy, cert)
        if why:
            problems.append('the IMA signature of %s does not verify with %s: the kernel '
                            'refuses the policy and the boot freezes (%s)'
                            % (IMA_POLICY, IMA_KEY, why))
        if bundle:
            why = cert_trusted(cert, bundle)
            if why:
                problems.append('%s is not signed by a key the kernel trusts (%s): .ima '
                                'refuses it and the boot freezes (%s)' % (IMA_KEY, bundle, why))
    return problems, not problems


def check_manifest(manifest_path, dev_packages):
    with open(manifest_path) as f:
        installed = {l.split()[0] for l in f if l.split()}
    leaked = sorted(p for p in set(dev_packages) - set(PRODUCTION_ALSO) if p in installed)
    return ['development package in the release image: %s' % p for p in leaked]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--dev-recipe', required=True)
    ap.add_argument('--static', action='store_true')
    ap.add_argument('--manifest')
    ap.add_argument('--rootfs')
    ap.add_argument('--kernel-config')
    a = ap.parse_args(argv)

    dev = parse_dev_recipe(a.dev_recipe)
    if not dev['packages']:
        print('check-release-no-dev: no IMAGE_INSTALL found in %s' % a.dev_recipe, file=sys.stderr)
        return 1
    checks, unknown = required_checks(dev)
    problems = ['the dev recipe adds %s, which has no release check in this script' % u
                for u in unknown]
    if not a.static:
        if not (a.manifest and a.rootfs):
            ap.error('--manifest and --rootfs are required without --static')
        problems += check_manifest(a.manifest, dev['packages'])
        fs = Rootfs(a.rootfs)
        problems += check_rootfs(fs, checks)
        ima_problems, ima_verified = check_ima_loadable(fs, a.kernel_config)
        problems += ima_problems

    if problems:
        for p in problems:
            print('check-release-no-dev: %s' % p, file=sys.stderr)
        return 1
    if a.static:
        print('    dev recipe: %d packages, %d rootfs checks, every addition covered'
              % (len(set(dev['packages'])), len(checks)))
    else:
        print('    no development content: %d dev packages absent (%s expected in both), '
              'rootfs checks %s'
              % (len(set(dev['packages']) - set(PRODUCTION_ALSO)),
                 ', '.join(sorted(PRODUCTION_ALSO)), ', '.join(sorted(checks))))
        if ima_verified:
            print('    %s: security.ima verifies with %s, which chains to '
                  'CONFIG_SYSTEM_TRUSTED_KEYS of %s' % (IMA_POLICY, IMA_KEY, a.kernel_config))
    return 0


if __name__ == '__main__':
    sys.exit(main())
