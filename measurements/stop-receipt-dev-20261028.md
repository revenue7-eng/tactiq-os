# Development image: a stop receipt checked off the device, against a challenge chosen off the device (2026-10-28)

## Questions

1. Can a party other than the device confirm, offline, that the AI agent on
   the device is stopped at the moment it asks?
2. Does that confirmation rest on the TPM, or only on the stop service's
   word?
3. Does the check refuse the same receipt when it is presented against
   another challenge or another build?

## Setup

- Board: the Rock 5A reference board (Infineon TPM, firmware
  `7.87.19691.2`), slot A, development image delivered as `op1`, built from
  the branch merged as tactiq-os #286. The board's `/etc/tactiq-release` was
  not captured in this run; the image is identified by its boot
  measurements, below, not by a revision string.
- Boot measurements: after a cold start, PCR 0 to 9 equal
  `pcr-ref-op1-20261028.json` for slot A in full (`~/bin/pcr-match`, its
  result line is in `pcr-match.log`). The PCR values read on the board are
  in `board-session.log`.
- Stop state before the run: stop counter `8129` (odd, stopped), set by
  `tactiq-stop trip` in the op1 run of 2026-10-28.
- Challenge: 32 bytes drawn on a separate PC with
  `tactiq-stop-verify nonce` (from `/dev/urandom`), written to `nonce.txt`,
  carried to the board on a USB drive.
- On the board: `tactiq-stop status <nonce>`, output to the USB drive. The
  device's `ak.pub` and `device_id` copied to the same drive. Full console
  session: `board-session.log`.
- Verifier: `tactiq-stop-verify` from tactiq-attest `df8c50c` (#27),
  `tools/stop-verify`, run on the PC, offline.
- AK: `ak.pub` here is the file copied from `/data/tactiq/keys/ak.pub` on
  the board, byte for byte the `ak.pub` in `tpm-quotes-dev-20261015/`. Its
  TPM name, `000b35c0941662473b6dc78ce636d83dfcaf1bbdfa68bb69121dd9b3c0b414df0a0a`,
  equals `ak_name` in `registration-TACTIQ-BENCH-001-rc14.json` in the
  `l3-evidence-rc14.tar.gz` asset of the v2.1.0-rc14 release. The signature
  of that record was not checked in this run.

## Files

| file | what |
| --- | --- |
| `receipt.tqsr` | the receipt as the board wrote it (647 bytes) |
| `nonce.txt` | the challenge, hex |
| `ak.pub` | the device's AK, `TPM2B_PUBLIC` |
| `device_id.txt` | the device id file as copied from the board |
| `pcr-ref-op1-20261028.json` | the reference of the build, from `mk-pcr-reference.py` |
| `board-session.log` | the console session on the board |
| `pcr-match.log` | the comparison of the board's PCR 0 to 9 with every reference on the PC |
| `verify.log` | the check against the challenge and the reference |
| `verify-other-nonce.log` | control: the same receipt against a fresh challenge |
| `verify-slot-b.log` | control: the same receipt against the slot B reference |
| `check.sh` | runs the three checks again |

Sums of every file are in `../SHA256SUMS`.

## Results

| check | result |
| --- | --- |
| against the challenge and the slot A reference | `VERDICT STOPPED`, exit 0 |
| counter, as read and signed by the TPM | 8129 (odd) |
| bound to the challenge | yes |
| policy digest in the record | `60e962b74b1bf258d0fe5f21b25cccfb288c9b6f7ab71550dd385b3ebe92063a` |
| against a fresh challenge | refused: `nonce: the receipt answers another challenge` |
| against the slot B reference | refused: `quote: the boot PCRs are not the reference build's` |
| SELinux denials in the boot, by the journal | 0 |

## What this establishes

- Question 1: yes, for this board and this moment. The answer was made
  after the challenge was chosen off the device, and was checked off the
  device with nothing from the device but the receipt and the AK.
- Question 2: on the TPM. The counter value in the receipt is the TPM's own
  read of the stop counter (`NV_Certify`), and the counter is odd. By the
  stop rule an odd counter is a stop whatever the service reports; the
  service's own word decides only for an even counter (an operator release
  found or not).
- Question 3: yes. The controls keep their raw output (`verify-*.log`).

## What this does not establish

- That every call is refused at an odd counter. That is the rule of the
  measured build named by PCR 0, 1, 8, tested separately on the board in
  the op1 and tb1 runs of tactiq-os #285 and #286, not in this run.
- That the AK is used only by the stop service. It is shared with the
  attestation agent on this image.
- Anything about a release image, another board or a later boot.
- That the AK registration record itself verifies: only its `ak_name` was
  compared.

## Horizon

The record holds as long as the verifier's rules do: a change to
`verify_stop_receipt` in tactiq-attest or to the receipt format means
running `check.sh` again with the new verifier. A later trip, recover or
reflash of the board does not change it: it is about one receipt, made once.

## Reproduce

Build the verifier from tactiq-attest at `df8c50c` or later:

```
cargo build --release --manifest-path tools/stop-verify/Cargo.toml
```

Then, in this directory:

```
sh check.sh /path/to/tools/stop-verify/target/release/tactiq-stop-verify
```

Expected last line: `ALL CHECKS PASSED`, exit status 0.
