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
                postinst logging, no IMA policy, no development audit log path.

Two modes:

  --static      read the dev recipe only and fail if it adds anything this
                script has no check for (CI: a new dev addition cannot land
                without a release check, or an explicit "build only" entry);
  default       also read --manifest and --rootfs and check the release.

Usage:
  check-release-no-dev.py --dev-recipe recipes-core/images/tactiq-image-dev.bb --static
  check-release-no-dev.py --dev-recipe recipes-core/images/tactiq-image-dev.bb \\
      --manifest <image>.manifest --rootfs <image>.ext4

Exit status 0 when everything holds, 1 otherwise. Reads files and runs
debugfs read-only; changes nothing.
"""

import argparse
import re
import subprocess
import sys

# Packages the dev recipe installs that production carries anyway.
PRODUCTION_ALSO = {
    'audit': 'RDEPENDS of dbus-1, shadow-base, libsemanage2 and '
             'policycoreutils-setfiles (tactiq-image.bb); not started at boot',
    'tpm2-tools': 'RDEPENDS of tactiq-agent, which reaches the TPM through it; '
                  'leaves production when the agent moves to tss-esapi',
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
CLASS_CHECKS = {'ima-evm-rootfs': 'no-ima-policy'}
INHERIT_CHECKS = {'create-spdx': None}   # None: build side only, nothing in the rootfs
VARIABLE_CHECKS = {'EXTRA_USERS_PARAMS': 'root-locked'}
HOOK_CHECKS = {
    'tactiq_dev_audit_log': 'audit-log',
    'tactiq_ima_policy_mode': 'no-ima-policy',
}

DEV_AUDIT_PREFIX = '/data/tactiq/measurement/'


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
    if 'no-ima-policy' in checks:
        if fs.read('/etc/ima/ima-policy') is not None:
            problems.append('/etc/ima/ima-policy is present (development IMA policy)')
    if 'audit-log' in checks:
        text = fs.read('/etc/audit/auditd.conf')
        if text is not None:
            for l in text.splitlines():
                m = re.match(r'^\s*log_file\s*=\s*(\S+)', l)
                if m and m.group(1).startswith(DEV_AUDIT_PREFIX):
                    problems.append('/etc/audit/auditd.conf logs to the development '
                                    'measurement tree: %s' % m.group(1))
    return problems


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
        problems += check_rootfs(Rootfs(a.rootfs), checks)

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
    return 0


if __name__ == '__main__':
    sys.exit(main())
