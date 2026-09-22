# RIM signer is refused as a bundle signer (2026-09-22)

## Question

`gen-pki.sh rim` and `rim-prod` issue a leaf from the Signing CA whose only
extended key usage is the private OID `2.25.209288284150790823604684143005475146259`
(critical, no codeSigning). The leaf signs the RIM (RELEASE_INTEGRITY.md §5).
It chains to the same Root CA as the RAUC bundle signer, so the property that
keeps it out of the update path is the purpose check in RAUC, not the chain.

The question: does the check the board runs refuse a bundle signed by this
leaf, when the signing side checked nothing?

## Setup

- `rauc 1.15.2`, the native binary from the release build's sysroot
  (`sysroots-components/x86_64/rauc-native`), run on the build host with
  `glib-2.0-native` on `LD_LIBRARY_PATH`. libcrypto came from the host.
- Input: a dev-signed verity bundle from the development build,
  `tactiq-bundle-tactiq-rock5a-20260921073045.raucb`. Read only; re-signed
  copies were written to a scratch directory and deleted afterwards.
- Keys: `pki/dev/signer.pem` (control) and `pki/dev/rim-signer.pem`, both with
  `pki/dev/signing-ca.pem` as intermediate. Keyring `pki/dev/root-ca.pem`.
- Config: `recipes-core/rauc/files/system.conf` from the tree, whose
  `[keyring]` section sets `check-purpose=codesign-rauc`.

## Cases

| Case | How it was signed | `resign` | `info`, tree `system.conf` | `info`, `-C keyring:check-purpose=codesign-rauc` |
| --- | --- | --- | --- | --- |
| signer | `rauc resign --no-verify` with keyring and tree config | 0 | 0 | 0 |
| rim-signer | same as above | 1 | not reached | not reached |
| rim-unchk | `rauc resign --no-verify`, no keyring, no config | 0 | 1 | 1 |

`rim-signer`: RAUC verifies the new signature against the keyring before
writing the bundle, and refuses with
`Signer certificate does not specify extended key usage code signing` and
`Verify error: unsuitable certificate purpose`. This is the signing tool
guarding itself, which says nothing about a tool that does not check.

`rim-unchk` is the case that matters. With no keyring RAUC skips verification
(`No keyring given, skipping signature verification`) and writes the bundle,
as any signing tool outside our control would. Verifying that bundle with the
tree's `system.conf` gives the same two messages and exit code 1. The result
is the same with the full config and with `check-purpose` alone, so the
refusal comes from the purpose check.

## Result

The board-side verification refuses a bundle signed by the RIM leaf, and
accepts the same bundle signed by the bundle signer. A holder of the RIM key
cannot produce an update the board installs.

## Limits

- Not run on the board. `rauc info` and `rauc install` share the signature
  verification, but the board's RAUC version was not checked against 1.15.2
  in this run.
- Only the dev hierarchy was used. The release leaf has the same extensions
  (same `gen-pki.sh` code path, `rim-prod`); the test is to be repeated with
  the release keys in the ceremony environment.
- The IMA leaf (`ima-signer.pem`, no extended key usage at all) was not tested
  here. `gen-pki.sh` states that RAUC must not accept it; that claim remains
  unmeasured.

## Reproduce

With `RAUC` set to a rauc binary able to run on the host, `B` to any
dev-signed bundle and the repository as the working directory:

    $RAUC resign --no-verify \
      --cert=pki/dev/rim-signer.pem --key=pki/dev/rim-signer.key.pem \
      --intermediate=pki/dev/signing-ca.pem "$B" /tmp/rim.raucb
    $RAUC info --conf=recipes-core/rauc/files/system.conf \
      --keyring=pki/dev/root-ca.pem /tmp/rim.raucb

The second command must fail with `unsuitable certificate purpose`. Repeat
with `signer.pem` and `signer.key.pem` as the control; it must succeed.
