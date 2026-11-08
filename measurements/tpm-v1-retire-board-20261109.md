# Development image: the v1 agent's TPM objects removed from the bench board (2026-11-09)

## Questions

1. Which persistent TPM objects does the bench board still hold besides the
   AK, and what are they?
2. Can the objects the v1 agent left behind be removed without touching the
   AK the agent uses now?
3. Does the agent keep attesting with that AK once they are gone?

## Why

DDR-004 (tactiq-attest) moved the agent from the v1 envelope, signed by
`tpm2_sign` with a key at `0x81010002`, to TPM quotes signed by a restricted
AK, and left the v1 objects in place: "retiring it is a separate step". The
current agent (tactiq-attest `crates/attest-tpm/src/lib.rs`, the comment on
`DEFAULT_AK_HANDLE`) never reads, writes or evicts `0x81010001`,
`0x81010002` or `0x81010003`, and says removing them from a device is a
separate, announced step. This record is that step for `TACTIQ-BENCH-001`.

The v1 key is a signing key without `restricted`: the TPM signs any digest
presented to it under that key, not only structures the TPM produced
itself. The v2 verifier rejects such a key as an AK (DDR-004 decision 4), so
nothing on the bench relies on it, and keeping it only keeps a key that
signs whatever it is given. `0x81010001` and `0x81010002` are also the
handles the TCG registry reserves for the RSA and ECC EK (DDR-005).

## Setup

- Board: the Rock 5A reference board `TACTIQ-BENCH-001` (Infineon TPM),
  slot B. `/etc/tactiq-release`: `tactiq-image-dev`, `v2.1.0-rc14`, release
  date `2026-10-12`.
- Tools on the board: tpm2-tools with tpm2-tss 4.1.3, as shipped in the
  image.
- Owner authorization of the bench TPM is empty, so `tpm2_evictcontrol -C o`
  needed no password.
- Console in `tpm-v1-retire-board-20261109/board-session.log`: the TPM
  commands of the run and the agent status after them, as pasted from the
  console. Other commands in the same console session, not about TPM
  objects, are left out.
- The board has no clock: every boot starts at `Oct 12 00:00` in the
  journal, so journal times do not order boots. Boots are told apart by the
  agent's PID and by the epoch in the upper bits of its counter.

## What was on the board

| handle | object | attributes | name |
| --- | --- | --- | --- |
| `0x81010001` | v1 owner primary, ECC P-256, AES-128-CFB | `fixedtpm\|fixedparent\|sensitivedataorigin\|userwithauth\|restricted\|decrypt` | `000b737031a2f0e4e52d6ea339de7ba696c182ee0bf68cfbbafa99ba709fc45abe7e` |
| `0x81010002` | v1 signing key, ECC P-256, ECDSA-SHA256 | `fixedtpm\|fixedparent\|sensitivedataorigin\|userwithauth\|sign` | `000b60ece7b62a9ba769e46a597605c2cd575844c2aa59953801d423c3c143bca2ea` |
| `0x81010003` | absent (`TPM_RC_HANDLE`, `0x18B`) | | |
| `0x81010100` | AK, ECC P-256, ECDSA-SHA256 | `fixedtpm\|fixedparent\|sensitivedataorigin\|userwithauth\|restricted\|sign` | `000b35c0941662473b6dc78ce636d83dfcaf1bbdfa68bb69121dd9b3c0b414df0a0a` |

Public points of the two removed keys, as `tpm2_readpublic` printed them
before removal, so that a v1 signature can still be checked:

- `0x81010001`: x `25ca1b9d43aa5ec61b5263d8b7fd5e9e1b8048029b820e928ce3cac917365af0`,
  y `2b71b7db0a7cd96a8e0b771c8bfc73abbb8cbda58126d032e78ef9e9f101d572`
- `0x81010002`: x `be66eda1dbf2e01827be2ba4f4db6b9236c4d25b7b35449270aa92aa389003c7`,
  y `d4e3edc3dd5028fe73965768bd2e4950bee568ff227dafe8603fcad2fc177a3e`

## Removal

1. `tpm2_evictcontrol -C o -c 0x81010002`: `action: evicted`. Persistent
   handles after it: `0x81010001`, `0x81010100`.
2. `tpm2_evictcontrol -C o -c 0x81010001`: `action: evicted`. Persistent
   handles after it: `0x81010100` alone.

The v1 key cannot be restored: it was created by `tpm2_create`, and no copy
of its private part is kept. The primary can be recreated from the same
template for as long as the owner seed is unchanged.

## Results

| question | result |
| --- | --- |
| 1 | two objects besides the AK, both the v1 agent's; the v2 AK at `0x81010003` is already gone |
| 2 | both removed; the AK at `0x81010100` has the same name after removal as before |
| 3 | the agent (PID 477, started at this boot) went on attesting every 30 s; the last line of `systemctl status`, asked after both removals, is `counter=137220849870`, written within 30 s before that status |

## Not established

- Only `TACTIQ-BENCH-001` was changed. Devices on the first OS version
  (with the v1 agent) keep their v1 key; whether anything trusts it there is
  not looked at here.
- That the AK's name matches the one recorded at its registration is what
  the agent's `verify_ak` checks before each use. This run shows the agent
  attesting, not a separate comparison against the registration record.
- No envelope written after the removal was checked off the device.
