# Design decision: runtime report of the loaded model

Status: **decision recorded, not implemented.**
Date: 2026-09-29. Tree: `main` @ `1a74449`.

This document exists to fix an architectural decision before code is written.
It describes intent. It does not describe the current behaviour of the system.
Nothing here may be cited as a property of any shipped release.

---

## 1. Scope and the claim it is built to support

The evidence a release publishes today lets a third party check that a given
board booted a given loader and kernel (PCR 0, 1, 4, 6, 8, 9, see
`scripts/mk-pcr-reference.py`). It says nothing about the model that runs on
that board.

The goal is one additional claim, worded exactly:

> The quote reports which model file the measured runtime loaded, and which
> constant tensors that runtime's execution plan references.

Not claimed, now or after implementation:

- that inference outputs are correct;
- that weights in memory are unchanged after load (the report is taken once,
  at load);
- that the runtime was not replaced after it started (that is the job of IMA
  appraisal and SELinux, not of this mechanism).

A file hash alone is not enough for the claim. A model file can be present and
verified on disk while part of it is never loaded into the execution plan.
The measurement is therefore taken from the interpreter after allocation, not
from the file.

---

## 2. Established state

### 2.1 Model and runtime exist only in the measurement branch

`git grep -l -i -E "tflite|teflon|mobilenet"` finds the runtime and the model
only in the NPU measurement setup:

- `recipes-core/images/tactiq-image-npu.bb`: dev-based, marked "NEVER
  released"; installs `tensorflow-lite-benchmark`, `libteflon`,
  `kernel-module-rocket`.
- `meta-tactiq-bsp-rockchip/conf/machine/tactiq-rock5a-npu.conf`: the
  release machine plus the `npu` override token, the `npu` machine feature
  and a different devicetree. The release machine carries none of these, by
  design, and the NPU machine is built in a separate build directory.
- `meta-tactiq-bsp-rockchip/recipes-utils/tensorflow-lite/tensorflow-lite-benchmark_%.bbappend`:
  bakes `mobilenet_v1_1.0_224_quant.tflite` into the image, provenance pinned
  by two hashes (tarball `d32432d2...1744166`, `.tflite` `ecc3a67c...7d20dd`,
  4276352 bytes). The float model pulled by the base recipe is a different
  upstream release.

The release image (`tactiq-image`) contains no model and no inference runtime.

### 2.2 NPU userspace in a release is a separate decision

`conf/distro/tactiq.conf:82` removes `opengl` and `vulkan` from
`DISTRO_FEATURES` as a hardening decision. `mesa.bbappend` enables
`teflon rocket` only under the `npu` override. Bringing the NPU stack
(rocket, Mesa Teflon, NPU devicetree) into a release moves the release
boundary. That is out of scope here (§7).

### 2.3 TFLite is already a pinned layer

`integration/LAYERS.lock:46` pins `meta-tensorflow-lite` at
`f87ee8eab434497e3a1f8329013a4af5415cbd1e`. The layer provides
`libtensorflow-lite_2.21.0`, `libtensorflow-lite-c_2.21.0`,
`tensorflow-lite-minimal_2.21.0` and others. Using it in a release does not
add an unpinned input.

### 2.4 PCR allocation in the tree

| PCR | Owner | Source |
|-----|-------|--------|
| 0, 1, 4, 6, 8, 9 | SPL and U-Boot, boot chain | `scripts/mk-pcr-reference.py` header |
| 0-7 | closed with a separator | same |
| 10 | IMA, executed and mapped code | `tactiq-ima-appraise.policy:66-68` |
| 11 | IMA, delivered artifacts labelled `tactiq_vault_data_t` | `tactiq-ima-appraise.policy:72` |
| 12 | IMA, device identity labelled `tactiq_agent_state_t` | `tactiq-ima-appraise.policy:81` |

PCR 11 already exists for "what was consumed": the policy comment names
model and doctrine hashes. The file-level measurement of a model is therefore
already designed, provided the model is delivered into the vault with that
label and the policy is loaded (§6, item 1).

---

## 3. Decision 1: CPU only in the first iteration

The runtime runs TFLite builtin kernels on the CPU. No NPU delegate, and no
XNNPACK delegate (§6, item 4). The release boundary in §2.2 is untouched.

Everything built here (model recipe, runtime service, report, reference,
verification step) carries over to the NPU unchanged. The NPU adds one input
to the report: the delegation map, which operations ran on the accelerator.

## 4. Decision 2: C++ API

The runtime links `libtensorflow-lite` (C++), built on the pattern of
`tensorflow-lite-minimal`. The report needs the execution plan, each node's
inputs and each constant tensor's data. The stable C API is understood to
expose input and output tensors only; this is to be confirmed against the
2.21.0 headers before implementation (§6, item 2).

## 5. Decision 3: PCR 14

The runtime extends PCR 14.

- 0-12 are taken (§2.4).
- 16 is resettable without a reboot and would make the report meaningless.
- By UAPI convention systemd may write 11, 12, 13 and 15 when built with TPM2
  support. PCR 14 is conventionally used only by shim on UEFI, which does not
  exist in this boot chain. PCR 14 stays free even if the systemd build changes.

---

## 6. Measurement definition

After `AllocateTensors()` succeeds, the runtime computes:

1. `F = SHA-256` of the model file bytes, as read by the runtime.
2. Walk `execution_plan()` in order. For each node, record the operator code
   and version. For each input tensor of the node whose data is constant
   (defined below), record the tensor index at its first reference.
3. For each recorded constant tensor in that order: index, type, shape,
   byte length, `SHA-256` of the data.
4. `D = SHA-256` over the serialisation `tactiq-model-exec/1` of 1-3,
   defined byte for byte below. `scripts/mk-model-reference.py` computes
   the same `F` and `D` from the model file alone.

The runtime then extends PCR 14 with `D` and appends one record to its event
log: format name, model path, `F`, `D`, TFLite version, PCR index. One record
per model load; a verifier replays the log to reach the quoted PCR 14 value.

A model that is present and verified on disk but only partly loaded yields a
different `D` from the reference. That is the case the report is built to
catch.

### Serialisation `tactiq-model-exec/1`

This subsection is normative. The runtime and `scripts/mk-model-reference.py`
both implement it; where either disagrees with it, that implementation is
the bug.

All integers are little-endian. `D = SHA-256(S)`, where `S` is the
concatenation of:

1. The 19 ASCII bytes `tactiq-model-exec/1` followed by one zero byte.
2. `F`, 32 raw bytes.
3. `u32` number of operators in the primary subgraph (subgraph 0). Then,
   for each operator in its order in that subgraph: `i32` builtin code,
   taken as the larger of `deprecated_builtin_code` and `builtin_code` of
   its `OperatorCode`; `i32` operator version, 1 if absent; `u32` length of
   the custom operator name followed by the name bytes, where the length is
   0 unless the builtin code is `CUSTOM` (32).
4. `u32` number of constant tensors. Then, for each constant tensor in order
   of first reference: `u32` tensor index; `i32` tensor type (TFLite
   `TensorType`); `u32` rank followed by rank `i32` dimensions, taken from
   the tensor's `shape` in the model file; `u64` data length in bytes; 32 raw
   bytes of `SHA-256` of the data.

A tensor is constant when its buffer index is non-zero and the buffer carries
data, inline or through `offset` and `size`. Order of first reference: walk
the operators in order and each operator's inputs in order, skip optional
inputs (index -1), record each tensor once. On the CPU path without delegates
(section 3), the runtime's `execution_plan()` is exactly this operator order,
which is why the reference can be computed from the file alone.

A model in which a tensor of any subgraph carries buffer data and has
`is_variable` or `external_buffer` set has no `D`: TFLite refuses to load it
(checked in 2.21.0), so the runtime never measures it, and the reference
script refuses it as well.

### Reference and verification

- A new stdlib-only script, `scripts/mk-model-reference.py`, computes `F` and
  `D` from the published model file alone, in the same way
  `mk-pcr-reference.py` works from published boot files. Its output rides
  `SHA256SUMS` with the rest of the release.
- The verification page gains one step: replay the runtime event log to the
  PCR 14 value in the quote; recompute `D` from the published model with the
  published script; confirm the runtime binary's hash appears in the IMA log
  (PCR 10) and matches the release.

---

## 7. Out of scope

- NPU in a release (§2.2). Decided separately, when a customer or vertical
  needs latency the CPU cannot give.
- A model of our own. The mechanism does not depend on which model it
  measures.

## 8. Open items, to close before or during implementation

1. **IMA policy in a production image.** Resolved 2026-09-29: none.
   `security/coverage-rock5a.v2.1.0-rc13.yaml` (lines 240-242) records that
   the production image has no IMA signatures and no policy on disk, and
   `ima_policy=` reaches the kernel command line only under the
   `tactiq-dev-policy` override (`tactiq-rockchip-rk3588.inc:92`).
   `BOOT_CHAIN.md` is corrected in the same change. Consequence: in a
   release nothing measures the runtime binary, and dm-verity is not in the
   boot chain, so the PCR 14 report would have no anchor. One of the two must
   come first: rootfs dm-verity with the root hash inside the signed FIT
   (`docs/design/verity-fit-ab.md`), which puts the whole rootfs, runtime
   included, under PCR 8; or a measure-only IMA policy in the production
   image. This is a prerequisite, not part of this design.
2. **C API reach.** Confirm against `libtensorflow-lite-c_2.21.0` headers
   whether internal tensors are reachable; if they are, the C API may be
   preferable for a smaller surface.
3. **systemd TPM2 flag on the current image.** July boot logs show
   `systemd 259.5 ... -TPM2` (`measurements/selinux-enforcing-boot-prod-20260717.log:571`),
   and coverage files rc7 and rc10 (line 273) record it. Not re-recorded for
   rc11-rc13. Confirm with `systemctl --version` on the board at the next dev
   boot. Does not block §5.
4. **XNNPACK default delegate.** TFLite applies XNNPACK by default in many
   builds, which rewrites the plan. First iteration disables it so the plan
   equals the flatbuffer operator order and `D` is reproducible offline.
5. **Model location.** The runtime reads the model from the vault
   (`tactiq_vault_data_t`, PCR 11), not from the benchmark path in the rootfs.
6. **TPM access for the runtime.** A new SELinux domain for the runtime with
   access to `/dev/tpmrm0`, following the existing `tactiq_tpm` module.
