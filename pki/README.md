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

No IMA signing key is issued here, and `gen-pki.sh` has no branch that
produces one. This is a consequence of there being nothing to sign yet:
`CONFIG_IMA_APPRAISE=y` is set in the kernel fragment, but no on-disk
appraisal policy is deployed, so IMA measures and does not block (see
`BOOT_CHAIN.md` and `THREAT_MODEL.md`).

Issuing a key before the policy exists would put unexplained key material
in this directory without a consumer. When the appraisal policy lands, the
IMA branch is added to `gen-pki.sh` in the same change, following the RAUC
pattern above: leaf issued from the dev Signing CA, `digitalSignature`
only, no `codeSigning` EKU. This is listed as a Phase 3 prerequisite in
`KERNEL_HARDENING.md`.

Until then the repository `.gitignore` keeps stray `dev/ima-*` material
out of git: unlike the RAUC dev keys, whose publication is a deliberate
design property, nothing has been decided about IMA key handling.

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
