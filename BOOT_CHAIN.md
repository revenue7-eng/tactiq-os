# Boot chain

This document describes the chain of trust from the silicon root to
the running attestation agent — what each stage in the boot path
verifies and measures, where the chain is anchored, and the state of
each stage in v2.1.0-rc6. It sits alongside `DESIGN_PRINCIPLES.md`
(per-domain rationale), `THREAT_MODEL.md` (consolidated adversary
model), `ATTESTATION.md` (attestation framework),
`KERNEL_HARDENING.md` (kernel hardening posture), `SUPPLY_CHAIN.md`
(supply-chain self-assessment), `SECURITY.md` (vulnerability
disclosure policy), and `VERIFY.md` (consumer verification
procedure).

This is a v0.1 document. It iterates as stages move from current
state to fully verified.

Last reviewed: 2026-04-25.

## Status

The chain of trust described here is the architectural target.
Several of its stages are not yet anchored at hardware roots and not
yet enforcing verification at boundaries; these are named explicitly
in the per-stage status table below. The point of this document is
to make the present state legible — what is on, what is off, what
brings each off stage to on — rather than to describe a finished
posture that does not yet exist.

The chain is described at the distribution level. Per-platform
specifics — which TPM class is available, whether the SoC's OTP
fuses are burned, what vendor firmware blobs are in the early boot
path — vary between supported MACHINE configurations and are
documented per platform in `docs/machines/` as each platform
completes bring-up.

## Verified boot and measured boot

The chain of trust has two complementary properties. **Verified boot**
is the property that each stage cryptographically verifies the next
before transferring control — bad code does not run. **Measured boot**
is the property that each stage records what it executed into TPM
Platform Configuration Registers (PCRs) — what ran can be proved
later to a remote verifier.

The TactiQ OS architecture is designed for both. Verified boot stops
compromised execution at the boundary; measured boot makes the
boundary visible to attestation. They operate on the same stages and
serve different purposes: verified boot is local enforcement,
measured boot is remote provability. Either property can be present
without the other, and the per-stage status table below tracks them
separately.

## The chain

```
   SoC Boot ROM (immutable, vendor-shipped)
         │  verifies next stage  ── via OTP-fused public key root
         │  measures into PCR 0  ── via TPM driver in TEE/discrete TPM
         ▼
   Vendor early-boot firmware (TPL/SPL, DDR init)
         │  verifies next stage
         │  measures into PCR 1
         ▼
   U-Boot proper
         │  verifies FIT signature
         │  measures kernel + DTB + initramfs into PCRs 4–9
         ▼
   FIT image: kernel + device tree + initramfs (composite, signed)
         │  kernel takes over; IMA begins measuring file accesses
         │  extends PCR 10 with IMA runtime measurements
         ▼
   Kernel + initramfs (running)
         │  IMA appraisal verifies file signatures on access
         │  SELinux enforcing applies type-based MAC
         ▼
   Userspace under SELinux enforcing
         │  attestation agent reads PCR state, signs payload
         ▼
   Signed attestation payload to remote verifier
```

The diagram describes the target. The per-stage table below
describes the present state of each link.

## Per-stage status

| Stage | Verified | Measured | Notes |
|-------|----------|----------|-------|
| Boot ROM → vendor early-boot firmware | OFF | n/a (root) | Verification depends on OTP fuses being burned for the public key root. Fuses are not burned on the reference development hardware in current bring-up. |
| Vendor early-boot firmware → U-Boot | OFF | OFF | Depends on the previous stage; until the chain is anchored at the SoC ROM, this transition is not cryptographically gated. |
| U-Boot → FIT image (kernel + DTB + initramfs) | OFF | OFF | FIT image signing is not implemented in the current build pipeline. The U-Boot configuration does not enable FIT signature verification. Both halves of this stage are tracked in the supply-chain roadmap. |
| Kernel measures itself and initramfs | n/a | PARTIAL | Kernel TPM drivers are compiled in (`CONFIG_TCG_*`); IMA is configured at PCR 10. Whether the early boot stages successfully extended PCRs 0–9 before kernel handoff depends on the bootloader path being measured-boot aware, which it is not in current state. |
| Kernel runtime → file accesses | n/a | ON | IMA measures file accesses and extends PCR 10. This part of the measured-boot chain is functional in the present configuration. |
| Kernel runtime → file access enforcement | OFF | n/a | IMA appraisal is configured at the kernel level (`CONFIG_IMA_APPRAISE=y`) but the on-disk policy that tells the kernel which files require valid signatures is not deployed. Without policy, IMA measures but does not block. |
| Kernel → userspace MAC | ON | n/a | SELinux is enforcing from boot, with the targeted reference policy plus the TactiQ-specific modules from `meta-tactiq-selinux`. This is the strongest enforced boundary in the current chain. |
| Userspace → attestation payload | STUB | n/a | The agent at `/opt/tactiq/bin/tactiq-agent` is a stub. Full architectural specification in `ATTESTATION.md`, including the path from stub to TPM-quote-integrated implementation. |

The single ON row in the Verified column at the kernel-to-userspace
boundary, and the single ON row in the Measured column for IMA
runtime measurements, are the parts of the chain that are working
today. Everything above them in the boot order is either OFF or
PARTIAL. This is the gap surface, named explicitly so that it is
not invisible.

## Hardware anchor

Verified boot needs an anchor: a public key whose hash is burned
into one-time-programmable fuses in the SoC, such that the SoC's
boot ROM checks the first loaded stage against that key and refuses
to execute if the signature does not match. Without OTP burn, the
ROM accepts any signed-or-unsigned first stage, and the chain has
no cryptographic root.

In the current TactiQ OS bring-up, the OTP fuses on the reference
development hardware are not burned. This is intentional at this
stage: OTP burn is a one-way operation, and the production keyring
that would be embedded in the OTP root must reach a stable state
first. The production keyring itself is tracked separately in the
supply-chain area as a transition from the in-tree development RAUC
keyring to a CI-secret-provisioned production keyring.

The order of operations is therefore: production keyring first,
then verification of the keyring through extended deployment, then
OTP burn — the last step in the sequence, because it cannot be
undone. This is documented as a roadmap dependency rather than a
near-term step.

## Vendor firmware blobs

Most production-class ARM SoCs ship parts of the early boot chain
(typically TPL/SPL stages performing DDR initialization) as binary
blobs distributed by the silicon vendor. These blobs are not part
of the source-buildable artifact set, and the supply-chain posture
of the boot chain is bounded by what the vendor publishes about
them.

The TactiQ OS chain of trust starts at the SoC boot ROM and extends
from there. What the vendor blobs do between ROM execution and
U-Boot entry is, in the current generation of supported hardware,
accepted as part of the trust delegation to the silicon vendor.
Per-platform variation in this area — which blobs are in the path,
what the vendor publishes about them, what alternatives exist —
is tracked in `docs/machines/` as each platform completes bring-up.

This is named explicitly because vendor blob trust delegation is a
class concern in any ARM-based secure boot chain, not a TactiQ
OS-specific problem. Acknowledging it here puts the boundary in a
visible place rather than leaving it implicit.

## Anti-rollback

Signed boot artifacts protect against unauthorized code; they do
not on their own protect against authorized-but-old code. An
attacker with write access to the boot media could install a
correctly-signed image from an earlier release that has a known
vulnerability and downgrade the system into an exploitable state.

The defense is a generation counter that the bootloader compares
between the running slot and a candidate slot, refusing to boot a
candidate whose generation is lower than what the platform has
already accepted. RAUC's bundle metadata supports this; U-Boot can
enforce it through environment-stored counters.

In v2.1.0-rc6 the machinery exists at the RAUC layer but the
generation counter check at the bootloader is not enforced. This
is tracked alongside FIT image signing.

## Kernel command line

Kernel command-line parameters are passed by the bootloader to the
kernel at boot. They affect kernel behavior in ways that matter for
the security posture — for example, they can disable IMA appraisal
or change SELinux to permissive mode, both of which would silently
weaken the runtime guarantees described elsewhere in this
documentation.

Until FIT image signing is implemented, command-line parameters
travel through an unsigned bootloader and are therefore modifiable
by anyone who can write to the boot media. Once FIT signing is in
place, command-line parameters become part of the signed FIT
payload and are protected against modification along with the
kernel image itself.

This means the kernel command line is part of the chain of trust,
not a separate concern, and the current state is that this part of
the chain is not yet anchored. This is the same observation made in
`KERNEL_HARDENING.md`; it is mentioned here because the boot chain
is where it gets resolved.

## TPM class

The strength of the cryptographic root that anchors the
attestation produced by this chain depends on the TPM class
available on the platform. Discrete TPM 2.0 chips provide a
hardware-isolated root; firmware TPM (fTPM) implementations
provide a software-isolated root in the SoC's secure-world TEE. The
attestation framework operates the same way over both, but the
threat model parameters differ.

This variation is documented in `THREAT_MODEL.md` section 6 rather
than repeated here. It is mentioned at this point in the boot chain
documentation because the early-boot measurements that this chain
extends into the TPM are the most affected by TPM class — what the
ROM and TPL/SPL stages can extend depends on whether the TPM is
available to them at all, and on platforms where the fTPM is
brought up later in the boot than the discrete-TPM equivalent
would have been, the early-stage measurements may be incomplete.

## Recovery on verification failure

The RAUC A/B partition layout provides the recovery path when a
boot attempt fails. If the bootloader marks a slot as pending
(after a fresh update) and the boot does not complete successfully
within a configured number of attempts, the bootloader rolls back
to the previously known-good slot.

This is one of the parts of the chain that is functional in
v2.1.0-rc6: the RAUC system configuration in
`recipes-core/rauc/files/system.conf` defines the A/B slots, and
the bootloader environment carries the slot-state machine. The
recovery semantics work at the slot-switching level today, even
while the verification at higher stages of the chain is not yet
enforced.

When verified boot is fully implemented, a slot whose signature
fails verification will not be entered at all — the bootloader will
fall through to the alternate slot before any code from the failing
slot runs. This is a stronger property than the current behavior
(which detects failure after attempted execution) and is the target
state.

## Roadmap

The transitions that move the chain from current state to fully
verified, in dependency order:

1. **Production keyring through CI secrets.** Replace the in-tree
   `pki/dev/root-ca.pem` with a keyring loaded from CI-managed
   secrets at build time. Tracked in the supply-chain area; this is
   a prerequisite for everything downstream because OTP burn binds
   to whatever keyring is canonical at burn time.

2. **FIT image signing in the build pipeline.** Add signing of the
   composite kernel-plus-DTB-plus-initramfs image to the Yocto
   build, using the production keyring from step 1.

3. **U-Boot configuration for FIT signature verification.** Enable
   the U-Boot options that make the bootloader actually verify the
   FIT signature before loading. Without this, signed images can be
   produced but the bootloader does not check them.

4. **Anti-rollback generation counter enforcement.** Wire the
   generation counter from RAUC bundle metadata through to a
   bootloader-enforced check.

5. **On-disk IMA appraisal policy.** Deploy the policy that covers
   `/opt/tactiq/` and the `tactiq-*` systemd unit files, so that
   IMA enforces signatures on file access rather than only
   measuring.

6. **OTP fuses burn.** Burn the production-keyring public key hash
   into the SoC OTP fuses. This is the last step in the sequence
   because it is irreversible. Per-platform — happens on each
   target machine after that platform has reached confidence in
   the keyring.

7. **TPM-quote integration in the attestation agent.** Bring the
   attestation framework to the state described in
   `ATTESTATION.md` section "Attestation payload", in which the
   measured platform state is part of the signed payload.

Steps 1–4 can run in parallel with the kernel agent work tracked
in the attestation area. Steps 5–7 depend on the earlier ones in
the order shown.

## What this boot chain does not cover

- **Side-channel attacks against the SoC ROM.** The boot ROM is
  immutable code on the silicon die; attacks at this level
  (decapsulation, fault injection, voltage glitching) are out of
  scope for the current generation of supported hardware. Hardware
  selection is the appropriate mitigation, not OS-layer hardening.
- **Vendor firmware blob compromise.** As discussed above, the
  TactiQ OS chain delegates trust to the silicon vendor for the
  parts of the early boot path that are vendor-shipped binary
  blobs. The blobs themselves are not under TactiQ OS supply-chain
  posture.
- **Physical access during the bring-up window.** During first boot
  setup, before keys are sealed and the chain is fully active,
  physical access to the device is assumed to be controlled. The
  chain protects steady-state operation, not the initial
  provisioning step.
- **Boot performance optimization.** The number of measurements,
  the verification overhead, the time to first userspace are
  considerations that may matter for specific deployment scenarios.
  This document does not describe trade-offs between security
  posture and boot time.

## References

- `THREAT_MODEL.md` — consolidated adversary model, including
  per-platform variation in TPM class.
- `ATTESTATION.md` — attestation framework that consumes the
  measured boot chain.
- `KERNEL_HARDENING.md` — kernel hardening posture.
- `SUPPLY_CHAIN.md` — supply-chain self-assessment, including the
  production keyring transition that gates several boot chain
  steps.
- `recipes-core/rauc/files/system.conf` — RAUC A/B slot definitions
  and bootloader integration.
- `pki/dev/root-ca.pem`: current development RAUC keyring, shared
  with kernel module signing. Production keyring transition tracked
  separately.
- `docs/machines/` — per-platform bring-up status, including TPM
  class, OTP fuses state, and vendor firmware blob inventory per
  target.
