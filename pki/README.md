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
