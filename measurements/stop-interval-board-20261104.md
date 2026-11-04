# Development image: a stop that held between two receipts, checked off the device by the TPM clock (2026-11-04)

## Questions

1. Can a party other than the device confirm, offline and without the
   device's logs, that the AI agent stayed stopped between two moments it
   chose, not only that it was stopped at each of them?
2. Does that check refuse a pair between which the stop was lifted and set
   again, so that the counter is odd at both ends?
3. Does it refuse a pair between which the device rebooted, so that any
   build may have run in between?

## Setup

- Board: the Rock 5A reference board `TACTIQ-BENCH-001` (Infineon TPM,
  firmware `7.87.19691.2`), slot A. `release-board.txt` is the board's
  `/etc/tactiq-release`: `tactiq-image-dev`, `v2.1.0-rc14`, release date
  `2026-10-12`.
- Boot measurements: PCR 0, 1 and 8 as read on the board are in
  `pcr-board.txt`. The verifier compares the PCR 0, 1, 8 that the TPM
  quoted in each receipt with the slot A entries of
  `pcr-ref-cnt-20261102.json`; all four receipts match. PCR 2 to 7 and 9
  were not compared in this run.
- Stop state before the run: stop counter `8145` (odd, stopped).
- Challenges: four of 32 bytes, drawn on a separate PC with
  `tactiq-stop-verify nonce`, written to `n1.txt` to `n4.txt`, carried to
  the board on a USB drive.
- On the board (console in `board-session.log`):
  1. `tactiq-stop status <n1>` to `r1.tqsr`;
  2. about ten minutes later by the operator's watch, nothing done in
     between, `tactiq-stop status <n2>` to `r2.tqsr`;
  3. `tactiq-stop recover` with an operator release for epoch 8146
     (8145 to 8146, running), then `tactiq-stop trip` (8146 to 8147,
     stopped), then `tactiq-stop status <n3>` to `r3.tqsr`;
  4. a cold start (poweroff, power pulled, power on), then
     `tactiq-stop status <n4>` to `r4.tqsr`.
  The operator release is not kept here.
- Verifier: `tactiq-stop-verify` from tactiq-attest `bb4fc23`
  (`tools/stop-verify`, DDR-007), run on the PC, offline.
- AK: `ak.pub` and `device_id.txt` are the files of
  `stop-receipt-dev-20261028/`, byte for byte. Its TPM name,
  `000b35c0941662473b6dc78ce636d83dfcaf1bbdfa68bb69121dd9b3c0b414df0a0a`,
  is what the verifier prints for every receipt here.

## Files

| file | what |
| --- | --- |
| `r1.tqsr` to `r4.tqsr` | the receipts as the board wrote them (646, 648, 647, 649 bytes) |
| `n1.txt` to `n4.txt` | the challenges, hex |
| `ak.pub` | the device's AK, `TPM2B_PUBLIC` |
| `device_id.txt` | the device id |
| `pcr-ref-cnt-20261102.json` | the reference of the build, from `mk-pcr-reference.py` |
| `release-board.txt` | `/etc/tactiq-release` of the board |
| `pcr-board.txt` | PCR 0, 1, 8 read on the board |
| `board-session.log` | the console of the board, three pieces of one run |
| `verify-r1.log` | `r1` checked alone |
| `verify-r1-r2.log` | the interval `r1` to `r2` |
| `verify-r2-r1.log` | control: the same pair in the wrong order |
| `verify-r2-r3.log` | the interval `r2` to `r3`, across recover and trip |
| `verify-r3-r4.log` | the interval `r3` to `r4`, across the cold start |
| `check.sh` | runs the five checks again |

Sums of every file are in `../SHA256SUMS`.

## Results

| check | result |
| --- | --- |
| `r1` alone, slot A | `VERDICT STOPPED`, counter 8145 |
| `r1` to `r2` | `VERDICT HELD`: counter 8145 at both ends, resetCount 380 and restartCount 0 at both ends, 782460 ms of TPM clock apart |
| `r2` to `r1` | refused: the second is not later |
| `r2` to `r3` | refused: the stop counter moved from 8145 to 8147 |
| `r3` to `r4` | refused: the TPM was reset in between (resetCount 380 then 381) |

Each receipt of a refused pair passes the single check on its own, so the
refusals are the interval check's.

The board's wall clock was wrong during the run: the receipts carry FAT
dates of 2026-10-12, and `r4`, written last, is dated before `r1`. The check
does not read it. The TPM clock gave about thirteen minutes for a gap of
about ten by the operator's watch; it is the TPM's count, not wall time, and
this record does not read it as a duration.

## What this establishes

- Question 1: yes, for this board and the interval from `r1` to `r2`. Both
  receipts answer challenges chosen off the device, and the check used
  nothing from the device but the two receipts and the AK. Between them the
  counter, as read and signed by the TPM, did not move, and the TPM did not
  reset or restart. Both quotes equal the reference, and within one TPM boot
  a PCR only moves forward, so the reference build ran throughout.
- Question 2: yes (`verify-r2-r3.log`).
- Question 3: yes (`verify-r3-r4.log`).

## What this does not establish

- That no command reached a process in the interval. The check covers the
  gateway's rule on this device; the process it guards was not observed.
- That the TPM clock difference is the time that passed. The clock can be
  moved forward (`TPM2_ClockSet`) by a holder of the owner authorization,
  which is empty on this image; it can never be moved back.
- That every call is refused at an odd counter. That is the rule of the
  measured build, tested on the board in the op1 and tb1 runs of
  tactiq-os #285 and #286, not in this run.
- That the AK is used only by the stop service. It is shared with the
  attestation agent on this image.
- Anything about a release image, another board, or a time outside the
  interval.

## Horizon

The record holds as long as the verifier's rules do: a change to
`verify_stop_receipt` or `verify_stop_interval` in tactiq-attest, to the
receipt format, or to the stop counter's definition (its TPM name) means
running `check.sh` again with the new verifier. A later trip, recover or
reflash of the board does not change it.

## Reproduce

Build the verifier from tactiq-attest at `bb4fc23` or later. In a clone of
tactiq-attest:

```
cargo build --release --manifest-path tools/stop-verify/Cargo.toml
```

Then, in this directory:

```
sh check.sh /path/to/tactiq-attest/tools/stop-verify/target/release/tactiq-stop-verify
```

Expected last line: `ALL CHECKS PASSED`, exit status 0.
