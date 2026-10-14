# Development image rc14: boot event log replay into PCR 0 to 9, and a quote bound to a workload key (2026-10-15)

## Questions

1. Does the boot chain of the rc14 development image leave a TCG event log
   that a verifier can replay to the quoted PCR 0 to 9? The earlier records
   in this directory carry no boot event log.
2. With that log and the IMA log, which of PCR 0 to 12 does the evidence
   show something about, and which hold nothing?
3. Can the quote's qualifying data carry a key thumbprint, so that the quote
   is checkably about one workload key?

## Setup

- Board: the Rock 5A reference board (Infineon SLB9670). The signed
  `firmwareVersion` is `00070057004ceb02`. Slot B. `/etc/tactiq-release`:
  `TACTIQ_IMAGE_NAME=tactiq-image-dev`, `TACTIQ_META_TACTIQ_GIT=v2.1.0-rc14`.
- Loader: its first boot event names `U-Boot 2026.10 (Oct 05 2026 - 21:35:33 +0000)`.
  Which build it is, is not recorded here, and its values are not compared
  with the rc14 RIM.
- Quote signed by the registered AK, persistent handle `0x81010100`, name
  `000b35c0941662473b6dc78ce636d83dfcaf1bbdfa68bb69121dd9b3c0b414df0a0a`
  (equal to `ak_name` in the signed rc13 registration record). `ak.pub` here
  is the output of `tpm2_readpublic` on the board and is byte for byte the
  `ak.pub` in `tpm-quotes-dev-20261002/`.
- Quote taken with
  `tpm2_quote -c 0x81010100 -l sha256:0,1,2,3,4,5,6,7,8,9,10,11,12 -g sha256`.
  The qualifying data is the RFC 7638 thumbprint (SHA-256 over the canonical
  JWK `{"crv":"Ed25519","kty":"OKP","x":...}`) of an Ed25519 public key
  generated for this run off the board, `x` in hex:
  `17aa9dffa8c80335dd534317985569523523e0633a600b93775e5d0b60d18930`.
  It is not a verifier's challenge.
- Right after the quote: the IMA log copied from
  `/sys/kernel/security/ima/ascii_runtime_measurements`, and the boot event
  log copied from `/sys/kernel/security/tpm0/binary_bios_measurements`.
- Files moved off the board on a USB drive. Their SHA-256, taken on the board
  before the copy and again here:

| file | sha256 |
| --- | --- |
| `ak.pub` | `7305eb2f5c44527681eefff026fcfbd86a98ecbe0565a2b12c721ecd3d4a04bd` |
| `quote.bios.log` | `bdd960f24421c225f8a04ad568ed85cf22e71d5d1387727b7e71677912c7575e` |
| `quote.ima.log` | `28a16fa2a2a3c0783092ebaecc0359778edc5e7adf13cb3f3d711edf6f78f763` |
| `quote.msg` | `d3e2a352ebe51431b077ec853c469f2b5e6e09106c5b09a4a2eabba7b8c1bdad` |
| `quote.pcr` | `b4b18805e70cdff4dc5795ce231f16ee991ec855931ef9d183820573cd3ff6fc` |
| `quote.sig` | `612bd81b47f8f8f0a1804bdb8b267946475e5d233cc6ca9f6d978f1c65ee6beb` |

## Results

| | value |
| --- | --- |
| quote under `ak.pub` | verifies |
| qualifying data | equals the thumbprint of the key above |
| `resetCount` (signed) | 335 |
| `restartCount` (signed) | 0 |
| TPM clock (signed) | 976993925 ms |
| PCR values | reproduce the signed `pcrDigest` |
| first IMA entry `boot_aggregate` | equals sha256 of quoted PCR 0 to 9 |

Boot event log, SHA-256 bank (the log also carries SHA-1), replayed per PCR:

| PCR | events in the log | replay equals quote |
| --- | --- | --- |
| 0 | `EV_S_CRTM_VERSION` (U-Boot 2026.10), `EV_POST_CODE` `atf-1`, `atf-2`, `atf-3`, a second `EV_S_CRTM_VERSION` with the same text, `EV_SEPARATOR` | yes |
| 1 | `EV_TABLE_OF_DEVICES` `dts`, `EV_PLATFORM_CONFIG_FLAGS`, `EV_SEPARATOR` | yes |
| 2, 3, 5, 7 | `EV_SEPARATOR` (`0xFFFFFFFF`) and nothing else | yes |
| 4 | `EV_POST_CODE` `u-boot`, `EV_SEPARATOR` | yes |
| 6 | `EV_POST_CODE` `fdt-1`, `EV_SEPARATOR` | yes |
| 8 | `EV_COMPACT_HASH` `linux`, no separator | yes |
| 9 | `EV_COMPACT_HASH` `initrd`, no separator | yes |

IMA log, 170 entries, every SHA-1 template hash reconstructed:

| PCR | entries | replay equals quote |
| --- | --- | --- |
| 10 | 168 | yes |
| 11 | 0 (quoted value is all zero) | yes |
| 12 | 2: `/data/tactiq/keys/device_id`, `/data/tactiq/keys/ak.pub` | yes |

The PCR 12 entry for `/data/tactiq/keys/ak.pub` carries
`sha256:7305eb2f...`, the SHA-256 of `ak.pub` in this directory.

The IMA policy as read on the board (`/sys/kernel/security/ima/policy`, not
part of the signed evidence), measure and appraise rules without the
`dont_` lines:

```
appraise func=POLICY_CHECK appraise_type=imasig
appraise func=MMAP_CHECK mask=MAY_EXEC
appraise func=BPRM_CHECK
appraise func=FILE_CHECK mask=MAY_READ obj_type=tactiq_vault_data_t
measure func=BPRM_CHECK
measure func=MMAP_CHECK mask=MAY_EXEC
measure func=MODULE_CHECK
measure func=FILE_CHECK mask=MAY_READ pcr=11 obj_type=tactiq_vault_data_t
measure func=FILE_CHECK mask=MAY_READ pcr=11 obj_type=tactiq_site_perm_t
measure func=FILE_CHECK mask=MAY_READ pcr=11 obj_type=tactiq_cartridge_t
measure func=FILE_CHECK mask=MAY_READ pcr=12 obj_type=tactiq_agent_state_t
```

## What this establishes

- Question 1: on this board with the rc14 development image, the loader
  leaves a crypto-agile event log in `binary_bios_measurements`, and its
  SHA-256 bank replays exactly to the quoted PCR 0 to 9.
- Question 2: the evidence shows what was recorded in PCR 0, 1, 4, 6, 8, 9
  (boot log) and in PCR 10 and 12 (IMA log). PCR 2, 3, 5 and 7 hold a
  separator and nothing else, so a match there confirms only that nothing
  was recorded. PCR 11 holds the reset value; under the policy read on the
  board, none of the three PCR 11 types was read in this boot before the quote.
- Question 3: the qualifying data is the thumbprint of the key above, under
  the AK's signature, so this quote can be checked as being about that key.

## What this does not establish

- That anything recorded here was appraised before it ran. The boot log
  records measurements and does not carry the result of a signature check;
  the IMA log does not show which entries the policy appraised. In TRACE
  terms (trace-spec section 3.1.5) the recorded layers are
  `measured-not-appraised` for a policy that requires appraisal.
- What the boot log digests correspond to. No reference values are compared
  here, including the rc14 RIM.
- Why PCR 0 carries two `EV_S_CRTM_VERSION` events with the same text.
- Freshness. The thumbprint was fixed before the quote, not chosen by a
  verifier, so the date of the quote is not established.
- That the attestation agent reports PCR 10 to 12. This is a manual quote,
  as in `tpm-quotes-dev-20261002.md`.
- How the release loader behaves, or anything for another board or image.

## Reproduce

```
cd measurements/tpm-quotes-dev-20261015
python3 check.py
```

Needs Python 3 and `tpm2_checkquote` (tpm2-tools). Expected last line:
`ALL CHECKS PASSED`, exit status 0. Exit status 1 means a check failed;
exit status 2 means none failed but at least one could not run, for example
with `tpm2_checkquote` missing, and the last line then says `NOT ESTABLISHED`.
Besides the quote, the thumbprint and both replays, `check.py` requires
`quote.pcr` to carry exactly the signed selection and its values, with every
other byte zero, ties the IMA log to the quote through `boot_aggregate`, and
checks the IMA entry for `ak.pub` against the file.

## Corrections
