# Signing hierarchies

Two independent PKI trees. A device trusts exactly one root.

## pki/dev/ — development

**The private keys in this directory are intentionally public.**

They are not a leak. Publishing them is a property of the design:
anyone can build a dev-signed bundle and confirm that a production
image rejects it. A secret dev key would protect nothing and would
make that check unreproducible from the outside.

This root is what the image trusts for RAUC updates: it is installed as
/etc/rauc/root-ca.pem and named in system.conf, which also sets
check-purpose=codesign-rauc to match the signer's extended key usage. Bundles
are signed by signer.pem; because that certificate is issued by
signing-ca.pem rather than by the root directly, the intermediate is
embedded in the CMS signature through --intermediate. A leaf-only
signature does not verify against the root.

Production images do not carry this root: it is installed only when
TACTIQ_KEYRING = "dev", and any other value halts the build until a keyring
is supplied through RAUC_KEYRING_FILE_EXTERNAL.

## pki/prod/ — production

Not in this repository, and never will be (see .gitignore).

Generated on an offline host. Only the certificates
(root-ca.pem, signing-ca.pem, signer.pem) leave that host.
The private keys never touch a networked machine and never
enter CI. Release bundles are signed offline via `rauc resign`.

Regenerate either tree with ./gen-pki.sh {dev|prod}.

## pki/dev/ima-* — IMA appraisal signing

`ima-signer.key.pem` signs every file in the `tactiq-image-dev` rootfs at
build time. The image applies `IMAGE_CLASSES += "ima-evm-rootfs"`, and the
class reads this key through the `IMA_EVM_*` variables in
`conf/distro/tactiq.conf`. `ima-signer.der` is the public half.
`system-trusted-bundle.pem` is compiled into the kernel keyring.
`root-ca.x509` carries the root certificate; its name follows the
encoding the kernel expects, but the file itself is PEM, not DER.

The private half is in-tree for the same reason as the RAUC development
key: without it, nobody outside can rebuild a dev image and verify that
its signatures are what they claim. A production image applies neither the
signing class nor the policy, so this key does not reach one.

`./gen-pki.sh ima` issues this leaf from the dev Signing CA and writes all
four files. It works inside an existing hierarchy rather than creating
one, and refuses if `ima-signer.*` is already there: a reissued key
invalidates every signature in a rootfs that was already built. To replace
the key, delete the four files first and rebuild the image.

The files committed here were made by hand in July, before the branch
existed. Rerunning the script produces a different key, because RSA generation is
not deterministic. The certificate comes out the same in every respect
that matters: extensions, criticality, issuer. What the branch reproduces
is the procedure, not the file.

Appraisal runs in `ima_appraise=log`. `KERNEL_HARDENING.md` records what
the switch to `enforce` is waiting on.

## pki/dev/module-signing/ — kernel module signing

This key is a build input rather than a rotatable credential. It is compiled
into the kernel's built-in keyring and is used to sign every kernel module.
Replacing it changes the kernel image and every `.ko`, so previously published
releases no longer reproduce.

Accordingly, the key is generated once for a given trust hierarchy and is never
rotated in place. `gen-pki.sh dev` neither generates nor modifies it: the script
refuses to run against an existing hierarchy, and regenerating one from scratch
requires re-creating this key separately.

Publishing this development key has no security impact while
`CONFIG_MODULE_SIG_FORCE` is disabled: unsigned modules continue to load, with
only a kernel warning. During the Phase 3 transition described in
`KERNEL_HARDENING.md`, production builds must instead supply
`TACTIQ_MODULE_SIG_KEY` from CI-managed secrets. Otherwise, possession of the
published development key would allow an attacker to produce modules accepted
by the production kernel.
