# tactiq-model-exec/1 across two implementations

## Summary

The format `tactiq-model-exec/1` has two independent implementations: the
runtime on the board, which measures a model after `AllocateTensors()`, and
`scripts/mk-model-reference.py`, which computes the same values from the model
file alone. Until this run they had never been compared against each other.

**Result:** they agree exactly, on two models, for `F`, `D`, the node count and
the constant-tensor count. `D` is therefore reproducible off the device, which
is the condition for extending a PCR with it.

The same run recorded the state of the measurement path. PCR 11 and PCR 14 are
both zero on this boot, and `/data/cartridges` does not exist, so the mechanism
is in place and carries no content yet.

Raw output: `logs/model-exec-crosscheck-20261029-board.log`.

## Environment

| Item | Value |
|---|---|
| Board | Radxa ROCK 5A (RK3588S) |
| Release | TactiQ OS v2.1.0-rc14 (tactiq-image-dev), slot A |
| Kernel | 6.18.52-yocto-standard-00164-g0e7b072c8239 |
| Root | dm-verity, dm-0 "rootfs" |
| SELinux | enforcing |
| IMA | policy loaded: measure 8, appraise 4 |
| TPM | TPM 2.0, IFX, firmware 7.87.19691.2 |
| Runtime under test | `/bin/tactiq-edge-measure`, sha256 `88ff2ae7a44cc80bbb9c0fe54c9522c6f7e43edb3252b942ca40d71bd5e5a706` |
| Reference script | `scripts/mk-model-reference.py`, sha256 `84785dbde6d12e5a22163627db23f418a85210c70bbdc74df8eff1eaca40091b` |
| Normative definition | `docs/design/model-runtime-measurement.md` section 6 |

The two model files are test models from the closed Edge repository, not
published here. They are identified below by their SHA-256, which is what `F`
is defined to be, so the identification is checkable without the files.

## Method

The reference script was run off the board on both files. A read-only script
was then carried to the board on a USB medium and run there; it printed
`sha256sum` of each file alongside the runtime's own output, so `F` is
confirmed twice by different code paths. The script changed nothing on the
board. It also read the current PCR values, the loaded IMA policy rules naming
a PCR, the IMA measurement log, and the cartridge path.

## Results

| model | field | off the board | on the board |
|---|---|---|---|
| test-int8.tflite | F | `b72506c69015541c68fbef582590fd332f0a85f413c73d8bb31f54df72882dc0` | same |
| test-int8.tflite | D | `b5a4ccc49ca30b1ec47992b26f6251315782f8eac06a86deadb154bed722632d` | same |
| test-int8.tflite | nodes / consts | 24 / 45 | 24 / 45 |
| test-float.tflite | F | `c7a03325c8cf20ba8166b3bcb8a80cffb7767e7604d69911ba0373149c7f0c40` | same |
| test-float.tflite | D | `117970dea2364d9669c2881c5666c55f41d0b955778bb1d18b0a5cc156df4565` | same |
| test-float.tflite | nodes / consts | 7 / 7 | 7 / 7 |

Inference succeeded after measuring in both cases, which is the other half of
the runtime's contract: measuring must not disturb the loaded model.

## State of the measurement path on this boot

| Item | Value |
|---|---|
| PCR 10 | `F718912CDAF9E6E3569E5AA88C5679A2177CE9E0742E8F5E8C9AC3B54A676A1B` |
| PCR 11 | all zero |
| PCR 12 | `FB7A2F9D70F4B0A320E458FDCACE9C26A63993001335A8DC692A6EE1D35991D0` |
| PCR 14 | all zero |
| IMA log entries | 233, none matching cartridge, tflite or gguf |
| `/data/cartridges` | does not exist |
| Cartridge anchor | `/etc/tactiq/cartridge-anchor/root-ca.pem`, 1931 bytes, present |

Four loaded rules name PCR 11 (`tactiq_vault_data_t`, `tactiq_site_perm_t`,
`tactiq_stop_release_t`, `tactiq_cartridge_t`) and one names PCR 12
(`tactiq_agent_state_t`). PCR 12 is non-zero, so the mechanism works where a
labelled file is read. PCR 11 is zero because no file carrying any of those
four types was read during this boot.

Consequence to state plainly: PCR 11 is a prepared channel with nothing in it.
Nothing outside may describe it as a working measurement of consumed artefacts
until a labelled read appears in the log and the PCR moves.

PCR 14 being zero is expected. The runtime prints `D` and does not extend a
PCR; its source says so in as many words.

## What this does not establish

`D` identifies the weights and the execution plan that referenced them. It
says nothing about whether those weights were trained or altered to behave
badly: a poisoned model has a stable `D` like any other.

The agreement shown here is for the CPU path with no delegates. With a
delegate the runtime's execution plan is rewritten, and the reference computed
from the file alone would no longer match by construction.

The format is specific to TFLite: it walks operator codes and constant
tensors of a flatbuffer. It does not apply to GGUF weights under a
llama.cpp-style runtime, which has no plan of that shape. An LLM path needs
its own format definition.

## When this stops holding

Run again after any of these, not on a date:

- either implementation changes: a new sha256 for `/bin/tactiq-edge-measure`
  or for `scripts/mk-model-reference.py`
- section 6 of the design document is amended
- a delegate is enabled on the runtime's load path
- the test models are regenerated
