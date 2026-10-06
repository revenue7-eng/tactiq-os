# Development loader: TPM reset on warm reboot, and IMA coverage of PCR 11 and 12 (2026-10-02)

## Questions

1. With the development loader, does a warm reboot start the TPM from
   `_TPM_Init`, as recorded on hardware for rc11, or does it leave the
   previous boot chain in the PCRs, as the disclosure added in #197 and
   carried into the rc12 and rc13 RIMs stated?
2. Which measurements in the development image reach the TPM without being
   appraised by IMA, and can a verifier tell that from the evidence?

## Setup

- Board `TACTIQ-BENCH-001` (Rock 5A, Infineon SLB9670), slot B,
  `/etc/tactiq-release`: `TACTIQ_IMAGE_NAME=tactiq-image-dev`,
  `TACTIQ_META_TACTIQ_GIT=v2.1.0-rc13`.
- Loader: a development loader, not the rc13 release loader: its PCR 0
  differs from the rc13 RIM. Which build it is, is not recorded here.
- Quotes signed by the registered AK, persistent handle `0x81010100`, name
  `000b35c0941662473b6dc78ce636d83dfcaf1bbdfa68bb69121dd9b3c0b414df0a0a`
  (equal to `ak_name` in the signed rc13 registration record). `ak.pub` in
  this directory is a copy of the one in `l3-evidence-rc13.tar.gz`.
- Quotes taken with `tpm2_quote -l sha256:0,...,12 -g sha256`; qualifying data
  is the ASCII label of the run (`tactiq-cold`, `tactiq-warm`), not a
  verifier's challenge.
- IMA logs copied from `/sys/kernel/security/ima/ascii_runtime_measurements`
  right after each quote. That file carries SHA-1 template hashes; `check.py`
  rebuilds the template data from the fields, checks it against the SHA-1 of
  every entry, and extends its SHA-256 into the SHA-256 bank.

Sequence: power off, power on (cold start), quote and log (`cold.*`);
`reboot` with power kept on (warm reboot), quote and log (`warm.*`).

## Results

| | cold | warm |
| --- | --- | --- |
| quote under `ak.pub` | verifies | verifies |
| `resetCount` (signed) | 242 | 243 |
| `restartCount` (signed) | 0 | 0 |
| PCR 0 to 9 | as below | identical to cold |
| PCR 11, 12 | as below | identical to cold |
| TPM clock (signed) | 605753465 ms | 605872757 ms, 119292 ms after cold |
| first log entry `boot_aggregate` | equals sha256 of quoted PCR 0 to 9 | equals sha256 of quoted PCR 0 to 9 |
| PCR 10 | replay of 169 entries equals quote | replay of 167 entries equals quote |

PCR 2, 3, 5 and 7 hold a single `EV_SEPARATOR` (`0xFFFFFFFF`) extension and
nothing else, as in the rc13 RIM.

IMA entries in PCR 11 and 12, both runs:

| PCR | file | SELinux type | IMA signature in entry |
| --- | --- | --- | --- |
| 11 | `/data/site/network-allow` | `tactiq_site_perm_t` | none |
| 11 | `/data/site/network-allow.sig` | `tactiq_site_perm_t` | none |
| 12 | `/data/tactiq/keys/device_id` | `tactiq_agent_state_t` | none |
| 12 | `/data/tactiq/keys/ak.pub` | `tactiq_agent_state_t` | none |

The IMA policy as read on the board (`/sys/kernel/security/ima/policy`, not
part of the signed evidence) has these measure and appraise rules:

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
measure func=FILE_CHECK mask=MAY_READ pcr=12 obj_type=tactiq_agent_state_t
```

## What this establishes

- Question 1: with this development loader, a warm reboot reset the TPM
  (`resetCount` +1 under the AK's signature, PCR 0 to 9 identical to the cold
  start). This agrees with the rc11 hardware record and contradicts the
  disclosure carried in the rc12 and rc13 RIMs, which #224 corrects in the
  tree.
- Question 2: the four entries above are measured; their replay reaches the
  quoted PCR 11 and 12. Under the policy read on the board, reads of
  `tactiq_site_perm_t` and `tactiq_agent_state_t` are measured and not
  appraised, and so are kernel modules (`MODULE_CHECK`).

## What this does not establish

- That the attestation agent reports PCR 10 to 12. The agent of this image
  quotes PCR 0 to 9 (`TACTIQ_PCR_SPEC` in its systemd unit, the selection of
  the release RIM), and its envelope carries no IMA log. PCR 10 to 12 here
  come from the manual quote described under Setup, not from the agent.
- How the rc13 release loader behaves on a warm reboot. Not observed.
- Why the TPM reset. SPL drives the TPM reset line, and the running system
  can drive the same GPIO, so a reset is not by itself evidence of a reboot.
- Whether any of the entries above was appraised. The policy is not measured
  into the log, so the evidence shows measurement only; "not appraised" comes
  from the policy as read on the board.
- Freshness. The qualifying data is a fixed label, so the date of the
  quotes is not established. Their order and the interval between them are:
  the signed TPM clock in the warm quote is 119292 ms after the cold one.
- Anything for another board or another image.

## Reproduce

```
cd measurements/tpm-quotes-dev-20261002
python3 check.py
```

Needs Python 3 and `tpm2_checkquote` (tpm2-tools). Expected last line:
`ALL CHECKS PASSED`, exit status 0. Exit status 1 means a check failed;
exit status 2 means none failed but at least one could not run, for example
with `tpm2_checkquote` missing, and the last line then says `NOT ESTABLISHED`.
Besides the quotes and the replay, `check.py` requires the `.pcr` files to
carry exactly the signed selection and its values, with every other byte
zero, and ties each log to its quote through `boot_aggregate`.

## Corrections

2026-10-05. The PCR 10 row gave whole-log entry counts (173 and 171); PCR 10
itself takes 169 and 167. `check.py` exited with the same status for a crash
as for a failed check, and did not look at the padding in the `.pcr` files:
a flipped bit there passed, because `tpm2_checkquote` does not read it
either. Both are fixed, and the TPM clock order and the `boot_aggregate` tie
are now reported. All four points come from an independent check of these
files by Capt Anil Sharma.

2026-10-06. Added under "What this does not establish": the attestation agent
of this image quotes PCR 0 to 9 only, so PCR 10 to 12 in this record come
from the manual quote, not from the agent. No measured value changed.
