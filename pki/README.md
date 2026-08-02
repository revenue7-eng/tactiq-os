# Signing hierarchies

Two independent PKI trees. A device trusts exactly one root.

## pki/dev/ — development

**The private keys in this directory are intentionally public.**

They are not a leak. Publishing them is a property of the design:
anyone can build a dev-signed bundle and confirm that a production
image rejects it. A secret dev key would protect nothing and would
make that check unreproducible from the outside.

Dev-signed bundles install only on images built with
TACTIQ_KEYRING = "dev". Production images do not carry this root.

## pki/prod/ — production

Not in this repository, and never will be (see .gitignore).

Generated on an offline host. Only the certificates
(root-ca.pem, signing-ca.pem, signer.pem) leave that host.
The private keys never touch a networked machine and never
enter CI. Release bundles are signed offline via `rauc resign`.

Regenerate either tree with ./gen-pki.sh {dev|prod}.

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
