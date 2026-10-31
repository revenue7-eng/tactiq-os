# A signed cartridge measured into PCR 11

## Correction

As first committed, the section "What this establishes" said that a verifier
replaying the IMA log "reaches the quoted PCR 11". That was wrong. PCR 11 is
not quoted. The agent's quote selection is `sha256:0,1,2,3,4,5,6,7,8,9`, set
in `recipes-core/tactiq-agent/files/tactiq-agent.service` and matching the
`pcr 0-9 sha256` line the board prints; the prover's built-in default is
narrower still, `sha256:0,1,2,3,4,5,6,7`, and `stop` uses `sha256:0,1,8`. PCR
10, 11, 12 and 14 are in none of them, in any bank.

What holds is weaker and stated here instead: PCR 11 is readable on the device
and replayable from the IMA log, and no signed statement covers it. Making it
part of a signed statement means widening the quote selection, which changes
the 5-byte selection field inside the canonical message and the composite over
it, so the verifier's expected selection and the published reference sets
change in step. The sentence in the body is corrected below.

Everything else in this report stands: the labels, the signature check, the
PCR movement, the log entries and the absence of denials were all read from
the board and are in the raw output.

## Summary, superseding an earlier record

Supersedes the state recorded in `model-exec-crosscheck-20261029.md`, which
reported PCR 11 as a prepared channel with nothing in it. That statement held
for the boot it describes and no longer describes the mechanism: PCR 11 now
carries cartridge measurements. The measurement of the format in that report
is unaffected and still stands.

## Summary

A cartridge signed by the development Cartridge Signer was placed on the data
partition, labelled, verified against the anchor shipped in the image, and
read. PCR 11 moved from all zero to
`24D79304B9620EB29C3D70C8AE26A183684C4E0809D5601539B570ED4D7B971A`, and the
IMA log carries one entry per cartridge file, the model among them, identified
by the same SHA-256 the manifest declares.

The model was measured without carrying an IMA signature. Trust in it was
established by a separate key, checked against the cartridge anchor. This is
the separation the cartridge scheme exists for, working on hardware under
SELinux enforcing, with no denials.

Raw output: `logs/cartridge-pcr11-20261030-board.log`.

## Environment

| Item | Value |
|---|---|
| Board | Radxa ROCK 5A (RK3588S) |
| Release | TactiQ OS v2.1.0-rc14 (tactiq-image-dev), slot A |
| Kernel | 6.18.52-yocto-standard-00164-g0e7b072c8239 |
| Root | dm-verity, dm-0 "rootfs" |
| SELinux | enforcing |
| IMA | policy loaded: measure 8, appraise 4 |
| Anchor | `/etc/tactiq/cartridge-anchor/root-ca.pem`, 1931 bytes, from `pki/dev/root-ca.pem` |
| Verifier | `/usr/bin/tactiq-cartridge-verify` |
| Runtime | `/bin/tactiq-edge-measure` |

## Method

The cartridge was built off the board with the Edge repository's
`tools/mk-cartridge.sh`, format `tactiq-cartridge/1`, signed with
`pki/dev/cart-signer.*` through `pki/dev/signing-ca.pem` to
`pki/dev/root-ca.pem`. The builder refuses a leaf whose only extended key
usage is not the Cartridge Signer OID, and verifies its own output.

It was delivered on a read-only USB medium, copied to
`/data/cartridges/test-int8`, labelled with `restorecon -RF`, then verified and
read on the board by a script that printed PCR 11 three times: before placing,
after the signature check, and after the model was loaded.

The cartridge files were deliberately not given IMA signatures. A model signed
with the IMA key would be signed with the key that validates executables,
which is the finding the cartridge scheme answers.

## Results

| Step | PCR 11 (sha256) |
|---|---|
| before placing | all zero |
| after the signature check | `24D79304B9620EB29C3D70C8AE26A183684C4E0809D5601539B570ED4D7B971A` |
| after the model was loaded | unchanged |

Labels after `restorecon`, all three files:
`system_u:object_r:tactiq_cartridge_t:s0`.

`tactiq-cartridge-verify` printed OK, naming the signer as the development
Cartridge Signer, the manifest as
`sha256:b9eb96de80842cb21b7102170eede711cda62ea8fe8dc7c772ba454f408e02d7` and
the model as `test-int8.tflite`, 730976 bytes,
`sha256:b72506c69015541c68fbef582590fd332f0a85f413c73d8bb31f54df72882dc0`.

The runtime then loaded the model from the cartridge and printed the same `F`
and `D` as recorded in `model-exec-crosscheck-20261029.md`, with inference
succeeding afterwards.

IMA log, 237 entries, three of them in PCR 11:

| file | sha256 in the log |
|---|---|
| `manifest.json` | `b9eb96de80842cb21b7102170eede711cda62ea8fe8dc7c772ba454f408e02d7` |
| `manifest.json.p7s` | `f0f6fa1219831355e05068c0c59a9a47b467c26b2c66708f537559a602c1a1aa` |
| `test-int8.tflite` | `b72506c69015541c68fbef582590fd332f0a85f413c73d8bb31f54df72882dc0` |

The model's entry uses the `ima-sig` template and ends at the path, with no
signature field, while the entry for `tactiq-cartridge-verify` itself in PCR 10
carries one. The log therefore records in its own structure that the model was
measured and not appraised.

`dmesg` showed no SELinux denial during the whole sequence.

## Why PCR 11 did not move on the load

IMA measures an inode once per boot. All three files were read by the
signature check, which reads the manifest, the detached signature and the
model, so all three entries and all three extensions happened there. The later
read by the runtime found them in the measured-file cache and extended nothing.

The consequence is about what PCR 11 can be claimed to say. It says that these
bytes were read on this boot. It does not say which process read them, how
many times, or what that process built from them. Binding the loaded execution
plan is what the PCR 14 report is for, and that report does not exist yet: the
runtime prints `D` and extends nothing.

## What this establishes

- A cartridge signed under a key that is not the IMA key is read on a release
  kernel under enforcing SELinux, measured into a PCR of its own, and verified
  against an anchor shipped in the read-only image.
- The file-level half of the claim about model identity works on the device: a
  verifier replaying the IMA log reaches the value PCR 11 holds and finds the
  model's hash in it. Corrected from the first version of this sentence, which
  called that PCR quoted. It is not: see the correction at the top.

## What it does not establish

- That the runtime loaded the whole model, or which tensors its execution plan
  referenced. That is `D` in PCR 14.
- Anything about the model's behaviour. A poisoned model measures like any
  other.
- Anything about the release image. This boot is `tactiq-image-dev`; the
  release image carries no IMA policy, so none of these measurements happen
  there.
- Anything about GGUF weights. The cartridge format references a model file and
  the runtime measured a flatbuffer; an LLM path needs its own definition.

## When this stops holding

Run again after any of these, not on a date:

- the IMA policy changes which types extend PCR 11, or their rules change order
- the cartridge anchor in the image changes, or the signer chain changes
- the SELinux file contexts for `/data/cartridges` change
- `tactiq-cartridge-verify` changes which files it reads, which would change
  which entries appear and in which order
- the measurement is repeated on the release image, where the policy is absent
  and the result is expected to differ
- the quote selection widens past `sha256:0-9`, which is what would turn any of
  this into a signed statement and would change the reference sets with it
