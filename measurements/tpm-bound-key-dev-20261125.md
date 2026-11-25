# Development image: a non-exportable key in the TPM, certified by the registered AK, signs a verifier's challenge (2026-11-25)

## Questions

1. Can the reference board's TPM hold a signing key whose private part cannot
   leave the chip (fixedTPM, fixedParent, sensitiveDataOrigin), with the
   ES256 algorithm a DPoP proof uses?
2. Does the registered AK certify that key with TPM2_Certify over a
   verifier's one-time value, so that a verifier with only public data can
   check the key's attributes and that it lives in this TPM?
3. Does the key sign a DPoP proof over a second one-time value of the
   verifier, so that holding the grant and old evidence is not enough?
4. With every file of the key that root on the board can read, can another
   TPM produce a signature with it?
5. Does the check refuse a key without fixedTPM and fixedParent that the
   same AK certified honestly?

## Why

Section 5.1 L4 of the OWASP AIMM Pillar 2 draft asks for a token-binding key
that is non-exportable and bound to an attested workload, with hardware key
attestation and a negative test that a copy of the runtime, or any key
material it can read, cannot produce a valid proof elsewhere. The candidate
`tactiq-tpm-bound-key` in aps-conformance-suite lists three limitations
against that: only the AK was shown non-exportable (the key in `cnf.jkt` was
generated off the board), there was no proof of possession, and there was no
freshness. This run takes the evidence for all three on the board.

## Setup

- Board: the Rock 5A reference board (Infineon SLB9670, firmware in the
  signed attest `00070057004ceb02`, which is 7.87.19691.2). Slot B. State
  block: `SELINUX Enforcing`, `IMA appraise-rules=4 measure-rules=8
  cmdline=none`, `ROOT root=/dev/dm-0`, `DM rootfs`, `SLOT B`.
  `/etc/tactiq-release`: `TACTIQ_IMAGE_NAME=tactiq-image-dev`,
  `TACTIQ_META_TACTIQ_GIT=v2.1.0-rc14`. The console scrollback before this
  run shows slot B was written from `tactiq-bundle-imaca-20261124.raucb`;
  the release string in the image was not raised for that build, so
  `v2.1.0-rc14` does not name the build exactly.
- Tree: `/mnt/d/tactiq-os` at `b7fd08b`. Nothing was built or written to the
  boot media for this run.
- Tools on the board: tpm2-tools 5.8 (`tpm2_sign -v`).
- AK: the registered AK, persistent handle `0x81010100`, the only persistent
  handle on the TPM in this run. Its name
  `000b35c0941662473b6dc78ce636d83dfcaf1bbdfa68bb69121dd9b3c0b414df0a0a`
  equals the one in `tpm-quotes-dev-20261015.md`; `ak.pub` here is byte for
  byte that record's `ak.pub` (same SHA-256).
- Parent: a primary created in the owner hierarchy with the default
  template (`tpm2_createprimary -C o -g sha256 -G ecc256`), not persisted.
- Working directory `/tmp/l4` (tmpfs). A first attempt in `/data/l4` failed:
  the new file got `tactiq_vault_data_t` (the label of `/data` since
  `data-root-label-board-20261123.md`), and the next tool run in
  `unconfined_t` could not read it back, with no AVC line in `dmesg`. Raw
  output in `board-console.log`. Not investigated further here.
- One-time values chosen by the verifier off the board: `n1.hex` for the
  certify, `n2.hex` for the DPoP proof, `n3.hex` for the control certify.
- `board-console.log` is the PuTTY scrollback (Copy All) of this run, from
  the tool check to the final `sha256sum`, cut at its first line. The
  scrollback before it belongs to other work on the board and is not part
  of this record.
- Files moved off the board as hex over the serial console
  (`hexdump -v -e '1/1 "%02x"'`, no base64 on the board) and rebuilt on the
  host. The SHA-256 of every file taken on the board (end of
  `board-console.log`) equals the SHA-256 of the rebuilt file
  (`SHA256SUMS`).

## Steps on the board

```
tpm2_createprimary -C o -g sha256 -G ecc256 -c primary.ctx
tpm2_create -C primary.ctx -G ecc256:ecdsa-sha256 \
  -a "fixedtpm|fixedparent|sensitivedataorigin|userwithauth|sign" -u bind.pub -r bind.priv
tpm2_load -C primary.ctx -u bind.pub -r bind.priv -c bind.ctx -n bind.name
tpm2_certify -c bind.ctx -C 0x81010100 -g sha256 -q <n1> -o certify.att -s certify.sig
tpm2_sign -c bind.ctx -g sha256 -d -o pop.sig pop.digest
tpm2_create -C primary.ctx -G ecc256:ecdsa-sha256 \
  -a "sensitivedataorigin|userwithauth|sign" -u exp.pub -r exp.priv
tpm2_load -C primary.ctx -u exp.pub -r exp.priv -c exp.ctx -n exp.name
tpm2_certify -c exp.ctx -C 0x81010100 -g sha256 -q <n3> -o exp.att -s exp.sig
```

`pop.digest` is the SHA-256 of `pop.signing_input`, the JWS signing input of
a DPoP proof (`typ dpop+jwt`, `alg ES256`, the key's JWK in the header,
`nonce` = `n2`), built off the board from `bind.pub` and written to the
board with `printf`. `pop.jwt` is that signing input with `pop.sig`
converted to the JWS `r||s` form.

## Results

`check.py` (offline, `cryptography`, no TPM) reads only the files of this
directory. Its output is `check.log`.

| check | result |
| --- | --- |
| AK is the registered AK (name and attributes fixedTPM, fixedParent, restricted, sign) | yes |
| `certify.att` is a TPM-generated TPM2_Certify signed by the AK | yes |
| qualifying data of `certify.att` | equals `n1` |
| certified name | equals the name of `bind.pub` (`000bda7d...e60f`) |
| attributes of `bind.pub` | fixedTPM, fixedParent, sensitiveDataOrigin, userWithAuth, sign; not restricted; ECC P-256, ECDSA SHA-256 |
| `pop.sig` | verifies under `bind.pub` over `pop.signing_input` |
| `pop.jwt` | verifies under the JWK in its own header; that JWK is the key of `bind.pub`; `nonce` equals `n2` |
| RFC 7638 thumbprint of the JWK (what a grant carries as `cnf.jkt`) | `vaQ9ov9hz9fIHwpWQQb3dzd_4thzwLWp7W7AD1g1Oi0` |
| signed clock, resetCount, restartCount | 2059677333 ms, 492, 0 |

Control and negatives, each with one expected reason:

| case | expected | got |
| --- | --- | --- |
| `exp.*`: key without fixedTPM and fixedParent, certified by the same AK over `n3` | `key_exportable` | `key_exportable` (AK signature verifies) |
| `certify.att` against `n3` | `nonce_mismatch` | `nonce_mismatch` |
| one byte of the certified name in `certify.att` changed | `certify_signature_invalid`, `key_not_certified` | same |
| one claim of the DPoP payload changed | `pop_signature_invalid` | same |
| `pop.jwt` against `n3` | `pop_nonce_mismatch` | same |

## Negative test on another TPM

`negative.sh` starts a fresh software TPM (swtpm) and gives it every file of
the key that root on the board can read: `bind.pub`, `bind.priv` (the private
part wrapped by the board's parent), `bind.ctx` and `primary.ctx` (the saved
contexts). Output: `negative-swtpm.log`.

| attempt | result |
| --- | --- |
| control: a primary created by the software TPM from the same template | succeeds |
| A: `tpm2_load` of `bind.priv` under that primary | refused, `TPM_RC_INTEGRITY` (`0x1DF`, integrity check failed) |
| B1: `tpm2_sign` with the board's `bind.ctx` | refused, `TPM_RC_SIZE` (`0x1D5`) at context load |
| B2: `tpm2_load` under the board's `primary.ctx` | refused, `TPM_RC_SIZE` (`0x1D5`) at context load |
| signature file produced | none |

A is the cryptographic refusal: the wrapped private part is protected with a
key derived from the board TPM's own seed. B1 and B2 fail earlier, because
the saved context format of the Infineon TPM and of swtpm differ; they show
the contexts are not usable elsewhere, not why.

## What this does not show

- The other TPM is a software TPM. No second hardware TPM was used.
- The owner authorization of the board TPM is empty. Root on the board can
  create keys under the owner hierarchy and can evict the AK; this run does
  not change that (`tpm-owner-auth`).
- On the same board, any process with access to `/dev/tpmrm0` and the key
  files can use the key. Non-exportable means it cannot be used on another
  TPM, not that only one process on this board can use it.
- The key is not bound to a PCR policy. It signs in any measured state; a
  changed state is detected only by comparing a quote with a reference.
- The key lives in `/tmp` and is lost at the next boot. Where a production
  key is kept (persistent handle or `/data`) is not decided here.
- The first measuring stage (SPL) is not authenticated, so "attested
  workload" rests on an unverified first stage.
- `iat` in the DPoP proof is the verifier's clock. The board has no trusted
  time.
- Development image only.

## Horizon

The result holds for this TPM while the AK `0x81010100` stays registered
under the name above. A TPM clear, a TPM firmware change, or a new AK means
running this again. A change to the key template (attributes, curve, scheme)
or to the DPoP proof form means running it again with the new template.

## Files

`tpm-bound-key-dev-20261125/`: `ak.pub`, `bind.pub`, `bind.name`,
`bind.priv`, `bind.ctx`, `primary.ctx`, `certify.att`, `certify.sig`,
`pop.signing_input`, `pop.digest`, `pop.sig`, `pop.jwt`, `exp.pub`,
`exp.name`, `exp.att`, `exp.sig`, `n1.hex`, `n2.hex`, `n3.hex`, `check.py`,
`check.log`, `negative.sh`, `negative-swtpm.log`, `board-console.log`.
`bind.priv` and the contexts are published on purpose: they are what the
negative test gives another TPM, and anyone can repeat it.
