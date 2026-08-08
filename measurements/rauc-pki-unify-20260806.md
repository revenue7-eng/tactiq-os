# RAUC signing PKI unified onto pki/dev/: hardware verification

Date: 2026-08-06
Board: Rock 5A (RK3588S), serial console ttyS2 @1500000
Tree: fix/rauc-pki-unify @ 3a13b21 (branched from v2.1.0-rc7, 0dd00d0)
Bundle: tactiq-bundle-tactiq-rock5a-20260806204512.raucb
        sha256 69c32ab9c3d25626fee1fc7b1b6b52a3ebd75ddcd0b8dcca725cf47aca56485b

## What was broken

The image shipped /etc/rauc/ca.cert.pem, subject "TactiQ Technologies /
TactiQ RAUC Dev CA". The private half of that CA is not in the repository
and not in the tag. Bundle signing was configured per-machine, in local.conf,
pointing at files excluded by .gitignore. `bitbake tactiq-bundle` from a
clean checkout failed with 'RAUC_KEY_FILE' not set. No party, including the
authors, could produce a bundle that image would accept from the tag alone.

## What changed

RAUC now uses the pki/dev/ hierarchy already used for kernel module signing.
The keyring installed in the image is root-ca.pem. RAUC_KEY_FILE and
RAUC_CERT_FILE are set in the recipe from ${LAYERDIR_tactiq-os}. The signer
is issued by an intermediate CA, so the intermediate is embedded in the CMS
signature via --intermediate, passed through BUNDLE_ARGS. system.conf sets
check-purpose=codesign, matching the signer's extendedKeyUsage.

Two intermediate states were rejected during the work. Both would have
produced a working bundle for the wrong reasons. Concatenating signer and
intermediate into RAUC_CERT_FILE does not work: rauc reads only the leaf.
Adding the intermediate to the device keyring does work, but it makes the
intermediate a trust root and defeats the two-level hierarchy.

## Build host results

    rauc info --keyring pki/dev/root-ca.pem -C keyring:check-purpose=codesign

  bundle built from the tree, no RAUC settings in local.conf:
    Verified inline signature by 'TactiQ OS DEVELOPMENT Signer (CI)'
    chain: signer, signing CA, root (three certificates)      exit 0

  same bundle resigned with an unrelated self-signed key:
    signature verification failed: self-signed certificate    exit 1

## Device results

Starting state: slot A booted (dev image), B inactive, both good,
BOOT_A_LEFT=3 BOOT_B_LEFT=3 BOOT_ORDER="B A".

1. First install attempt failed:

     LastError: signature verification failed:
                Verify error: certificate is not yet valid

   Cause: the board has no RTC. systemd had set the clock to its built-in
   epoch, 2026-03-13. The signer certificate is valid from 2026-07-14, so
   from the device's point of view it had not started yet. The bundle and
   the keyring were both correct.

   This is a property of the platform, not of the bundle. A node without a
   time source rejects a valid update. Recorded below as an open item.

2. After setting the clock manually, install succeeded. RAUC set
   BOOT_ORDER="B A" and activated rootfs.1.

3. Reboot: the system came up from slot B (production image: no IMA
   appraisal noise, root login requires a password), reached multi-user,
   and RAUC Good-marking completed, restoring BOOT_B_LEFT to 3.

4. Rollback was exercised by exhausting the counter in U-Boot
   (setenv BOOT_B_LEFT 0; saveenv; boot). The slot itself was left intact,
   so this tests the bootloader's selection logic without destroying B.
   U-Boot skipped B and booted A. After boot:

     Booted from: rootfs.0 (A)
     Activated:   rootfs.0 (A)
     rootfs.1 (B)  boot status: bad
     rootfs.0 (A)  boot status: good, booted

## Keyring selection is enforced, not documented

The development root must not reach a production image. Before this change
that was a sentence in RELEASE_INTEGRITY.md and a line printed by gen-pki.sh,
with nothing in the build to hold it: recipes-core/rauc installed pki/dev/
unconditionally. It now installs that root only when TACTIQ_KEYRING is "dev",
which conf/distro/tactiq.conf sets as the default. Any other value halts
parsing until RAUC_KEYRING_FILE_EXTERNAL supplies a keyring from outside the
tree.

Both branches were exercised on the build host:

  TACTIQ_KEYRING="dev" (default)
    RAUC_KEYRING_FILE="root-ca.pem"
    SRC_URI="file://system.conf file://root-ca.pem"

  TACTIQ_KEYRING="prod", no external keyring
    ERROR: TACTIQ_KEYRING is 'prod', not 'dev', but
    RAUC_KEYRING_FILE_EXTERNAL is unset. [...]
    ERROR: Parsing halted due to errors

There is no production hierarchy yet, so the gate blocks nothing today. It
is in place so that the first production build cannot inherit the
development root by omission.

## Open items observed, not introduced by this change

- No RTC: see device result 1. An update cannot be installed until the node
  has a plausible clock.
- The pki/dev/ signer expires 2026-10-12, three months from issue. A
  development hierarchy whose purpose is to make the check reproducible from
  outside should not expire on that scale.
- selinux-autorelabel.service fails on every boot of the dev image,
  including boots predating this work.
- The dev image carries a manually placed /etc/rauc/dev-ca.pem and an edited
  system.conf from 2026-08-06 11:15. Same trust root, different filename.
  Superseded by this change. The next dev image will carry root-ca.pem.
