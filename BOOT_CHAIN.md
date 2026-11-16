# Boot chain

This document describes the chain of trust from the silicon root to
the running attestation agent — what each stage in the boot path
verifies and measures, where the chain is anchored, and the state of
each stage. It sits alongside `DESIGN_PRINCIPLES.md`
(per-domain rationale), `THREAT_MODEL.md` (consolidated adversary
model), `ATTESTATION.md` (attestation framework),
`KERNEL_HARDENING.md` (kernel hardening posture), `SUPPLY_CHAIN.md`
(supply-chain self-assessment), `SECURITY.md` (vulnerability
disclosure policy), and `VERIFY.md` (consumer verification
procedure).

This document iterates as stages move from current state to fully
verified. The per-stage table is updated row by row as each stage
changes.

Last reviewed: 2026-11-16 (the chain diagram, initramfs, the root file
system row, the attestation row, the kernel command line).

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
         │  target: verifies the next stage against an OTP-fused key
         ▼
   Vendor early-boot firmware (TPL/SPL, DDR init)
         │  target: verifies U-Boot
         ▼
   U-Boot proper
         │  verifies the signature of the FIT configuration
         │  PCR 0: U-Boot version string
         │  PCR 1: device tree of that configuration, including /chosen
         │         bootargs (kernel command line, dm-verity root hash)
         │  PCR 8: kernel image
         ▼
   FIT image: kernel + device tree (signed configuration, no initramfs)
         │  kernel creates the dm-verity target from dm-mod.create=
         │  and mounts the root file system through it
         ▼
   Kernel (running), root file system under dm-verity
         │  IMA measures into PCRs 10–12 and appraises file signatures
         │  SELinux enforcing applies type-based MAC
         ▼
   Userspace under SELinux enforcing
         │  attestation agent has the TPM quote PCRs 0–9
         ▼
   Quoted attestation envelope to remote verifier
```

Lines marked "target" are not in place today. Every other line names
what the stage does on the default `fit` boot path; the per-stage table
below says what of it has been observed, on which image and under which
key. IMA measurement and appraisal are in the development image only
(rows below).

## Per-stage status

| Stage | Verified | Measured | Notes |
|-------|----------|----------|-------|
| Boot ROM → vendor early-boot firmware | OFF | n/a (root) | Verification depends on OTP fuses being burned for the public key root. Fuses are not burned on the reference development hardware in current bring-up. |
| Vendor early-boot firmware → U-Boot | OFF | OFF | Depends on the previous stage; until the chain is anchored at the SoC ROM, this transition is not cryptographically gated. |
| U-Boot → FIT image (kernel + DTB) | OFF | PARTIAL | U-Boot is built with FIT signature support (`CONFIG_FIT_SIGNATURE`, `CONFIG_FIT_FULL_CHECK`, merged from `files/fit-signature.cfg`), and the public key of the development signer is injected into the control FDT as a required key. The default boot method is `fit` (`TACTIQ_BOOT_METHOD`, with kernel signing derived from it): `extlinux.conf` names `/fitImage` as both `KERNEL` and `FDT`, so `sysboot` hands the FIT to `bootm` and the device tree comes from the signed configuration, not from `fdt_addr_r`. On the reference development hardware this path verified the configuration signature with the `dev-fit` key for both the kernel and the device tree, and a FIT with one byte of the configuration signature altered in memory was refused. A FIT with no signature at all has not been tested. This does not make the chain verified. The development keys are public by design (`pki/README.md`), so anyone can produce a FIT this bootloader accepts. `extlinux.conf` itself is not verified: pointing it at a raw `Image` sends U-Boot back to `booti`, which loads the kernel without any check. The bootloader holding the key is not verified by the stage below it. Setting `TACTIQ_BOOT_METHOD = "extlinux"` restores the raw `booti` path. Measured boot is enabled (`files/measured-boot.cfg`). U-Boot records the bootloader version string into PCR 0. With U-Boot 2026.10 it records the device tree into PCR 1, ahead of the `bootargs` variable (U-Boot 2024.07 put the device tree into PCR 0; `scripts/mk-pcr-reference.py` maps each version it knows). On the `bootm` path the kernel command line is `/chosen` of that device tree, so it is measured as part of it, including the dm-verity root hash; the `bootargs` variable is empty, and its PCR 1 event is the same in every slot. On the `bootm` path the kernel is measured into PCR 8: on the reference development hardware PCR 8 equalled one extend of the zero register with the SHA-256 of the deployed `Image`, and PCR 0 was unchanged. On the `booti` path the events labelled `linux` (PCR 8) and `initrd` (PCR 9) hash the event name instead of the data and do not depend on the kernel. Whether SPL verifies `u-boot.itb` itself is a separate question, not established here: SPL carries its own control FDT and this configuration sets no SPL symbols. |
| Kernel boot (no initramfs) | n/a | n/a | The kernel does not measure itself: U-Boot measures it into PCR 8 before handoff (row above). There is no initramfs: `CONFIG_BLK_DEV_INITRD=n` (`tactiq-security.cfg`), so nothing runs between the kernel and the root file system. Kernel TPM drivers are compiled in (`CONFIG_TCG_*`); IMA is configured at PCRs 10, 11 and 12 (rows below). |
| Kernel → root file system | ON (development image, observed) | via PCR 1 | The kernel creates the dm-verity target itself from `dm-mod.create=` (`CONFIG_DM_INIT`, `tactiq-verity.cfg`) and mounts the root file system through it. The root hash is in `/chosen` `bootargs` of the slot device tree (`tactiq-slot-dtb.bb`), which is inside the signed FIT configuration, so it is covered by the configuration signature and measured into PCR 1. `do_image_bootext4` refuses to build a boot partition whose FIT does not carry the root hash of the root file system next to it. On the reference development hardware a slot whose root file system did not match the root hash in its FIT stopped with a verity error before userspace, and U-Boot booted the other slot (`measurements/lockdown-userns-board-20261110.md`). Not yet observed on a release image under the release key. The development keys are public, so on that image this shows the mechanism, not that the root file system came from TactiQ. `CONFIG_DM_VERITY_VERIFY_ROOTHASH_SIG` is built, but the build produces no signed root hash, so the kernel does not check one. |
| Kernel runtime → file accesses | n/a | ON (dev) / OFF (production up to v2.1.0-rc14) | In the development image IMA measures file accesses and extends PCR 10 with executed and mapped code, PCR 11 with delivered artifacts labelled `tactiq_vault_data_t`, and PCR 12 with device identity labelled `tactiq_agent_state_t`. The `measure` rules live in `tactiq-ima-appraise.policy`, which reaches a device only through `ima-evm-rootfs` in `tactiq-image-dev.bb`; no build puts `ima_policy=` or `ima_appraise=` on the kernel command line (the `tactiq-dev-policy` override that did was removed in October 2026; the release command line is pinned in `security/cmdline-rock5a.json` and checked by `scripts/mk-release.sh`). Up to v2.1.0-rc14 the production image has neither, so no measure rules are loaded there and PCR 10, 11 and 12 carry no runtime measurements of the production system (`security/coverage-rock5a.v2.1.0-rc13.yaml`, lines 240-242). From the next release after v2.1.0-rc14 the production image installs `tactiq-ima-measure.policy` (`tactiq-ima-measure-policy`): the measure rules of the development policy and no appraise rule. That a production image loads it has not yet been observed on a board under the release key. The attestation agent quotes PCR 0 to 9 only (`TACTIQ_PCR_SPEC` in `tactiq-agent.service`), so these measurements reach no verifier. |
| Kernel runtime → file access enforcement | ENFORCE (dev) / OFF (production) | n/a | `tactiq-image-dev` signs its whole rootfs at build time (`IMAGE_CLASSES += "ima-evm-rootfs"`) and ships the appraisal policy as `/etc/ima/ima-policy`. Its command line carries no `ima_appraise=`, and the kernel default is enforce, so a failed appraisal blocks the access. The policy appraises execution, executable mappings and reads of `tactiq_vault_data_t`, which after the label split covers delivered artifacts alone; each requires a signature (`appraise_type=imasig`), and a digest in `security.ima` is refused. The development signer is public by design (`pki/README.md`), so on this image appraisal shows the policy and the signed rootfs working together, not that a file came from TactiQ. Record: `measurements/ima-imasig-board-20261109.md`. `tactiq-image.bb` does not apply the class: a production image has no signatures and no appraise rule (from the next release it measures only, row above). |
| Kernel → userspace MAC | ON | n/a | SELinux is enforcing from boot, with the targeted reference policy plus the TactiQ-specific modules from `meta-tactiq-selinux`. This is the strongest enforced boundary in the current chain. |
| Userspace → attestation payload | PARTIAL | n/a | The agent advances a monotonic TPM NV counter, reads the PCR bank, builds a fixed-size canonical envelope and has the TPM quote the PCR bank under a restricted attestation key, the quote committing to the envelope (tactiq-attest DDR-004). On the reference development hardware the agent attests with that key on the discrete SLB9670 (`measurements/tpm-v1-retire-board-20261109.md`); in that record no envelope it wrote was checked off the device. Quotes of PCR 0 to 12 by the same key on that board, taken with `tpm2_quote`, are checked in `measurements/tpm-quotes-dev-20261015.md`. The attestation key is not yet bound to the endorsement key. The envelope's final field is a digest over an empty evidence bundle. Architectural specification in `ATTESTATION.md`. |

The ON rows in the Verified column (the root file system under
dm-verity, observed on the development image, and SELinux at the
kernel-to-userspace boundary), and the IMA runtime measurements, which
are ON in the development image only, are the parts of the chain that
are working today. Everything above them in the boot order is either OFF or
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
first. The release keyring has been in use since v2.1.0-rc11; its keys are
held offline, not as CI secrets (`RELEASE_INTEGRITY.md` §2.3).

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

On the reference board the defense is a rollback floor held in the
TPM (`CONFIG_FIT_ROLLBACK_TPM`, patch `0010` in `recipes-bsp/u-boot`).
Each configuration of the kernel FIT carries a `rollback-index` inside
its signed node (`linux-yocto-fitimage.bbappend`; the value is
`TACTIQ_ROLLBACK_INDEX` in `release-rev.inc`). After the configuration
signature verifies, U-Boot refuses a configuration whose index is below
the floor and goes on to the other slot. The floor is a TPM NV bit
field under the platform hierarchy: only U-Boot writes it, before the
platform hierarchy is locked, and the TPM lets it only go up. U-Boot
raises it to the index of a configuration only when the OS has
confirmed the slot and U-Boot has booted that same configuration from
that slot before (recorded in `fit_seen_A` and `fit_seen_B`), so a
slot that has just been written never raises the floor on its first
boot, whoever wrote it. The index is raised at a declared security
boundary, not with every release.

Separately, RAUC refuses to install a bundle older than the installed
release (`min-bundle-version` in `system.conf`). That check is on
installation; the floor is on boot, and also covers an older image
written to a slot by other means.

Measured on the development build:
`measurements/rollback-floor-dev-20261108.md` and
`measurements/rollback-seen-dev-20261109.md`. No release up to
v2.1.0-rc14 carries either check. The development key is public, so
that an older release does not boot holds only under the release key.
An attacker who can write the loader area replaces the loader that
enforces the floor; against that attacker the floor holds only once the
loader is authenticated by the boot ROM (`THREAT_MODEL.md`, physical
attacker).

## Kernel command line

Kernel command-line parameters are passed by the bootloader to the
kernel at boot. They affect kernel behavior in ways that matter for
the security posture — for example, they can disable IMA appraisal
or change SELinux to permissive mode, both of which would silently
weaken the runtime guarantees described elsewhere in this
documentation.

On the default `fit` boot path the command line is `/chosen` `bootargs`
of the device tree in the signed FIT configuration. It is covered by
the configuration signature and measured into PCR 1 as part of the
device tree; the U-Boot `bootargs` variable is empty. The release
command line is pinned in `security/cmdline-rock5a.json` and checked
by `scripts/mk-release.sh`.

What is still open is the same as for the FIT itself (U-Boot row
above): `extlinux.conf` is not verified, and pointing it at a raw
`Image` takes the `booti` path, where the command line comes from the
unsigned `bootargs` variable. The bootloader that enforces the
signature is not yet authenticated by the boot ROM, and the
development keys are public. So the kernel command line is part of
the chain of trust, and it is anchored only as far as the FIT
signature is.

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

This is one of the parts of the chain that is functional today:
the RAUC system configuration in
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

1. **Release keyring.** Done in v2.1.0-rc11. Release builds use a
   release hierarchy instead of `pki/dev/root-ca.pem`. The keys are
   held offline on encrypted removable media, not as CI secrets
   (`RELEASE_INTEGRITY.md` §2.3). This remains a prerequisite for step 6, because OTP burn
   binds to whatever keyring is canonical at burn time.

2. **FIT image signing in the build pipeline.** Done. The build signs
   the FIT; release images are signed with the offline release FIT
   key (`RELEASE_INTEGRITY.md` §2.3).

3. **U-Boot configuration for FIT signature verification.** Enabled.
   The U-Boot row above records what has been verified on the
   reference hardware and with which key, and what is still not
   covered (`extlinux.conf`, an unsigned FIT, SPL).

4. **Anti-rollback enforcement.** Done on the development build: a
   rollback floor in the TPM, enforced by U-Boot on the kernel FIT
   (§ Anti-rollback). Not yet in a release.

5. **On-disk IMA appraisal policy.** Deploy the policy that covers
   `/opt/tactiq/` and the `tactiq-*` systemd unit files, so that
   IMA enforces signatures on file access rather than only
   measuring. Done for the development image, under the public
   development signer; a production image carries neither the
   signatures nor an appraise rule (from the next release after
   v2.1.0-rc14 it carries the measure rules alone).

6. **OTP fuses burn.** Burn the production-keyring public key hash
   into the SoC OTP fuses. This is the last step in the sequence
   because it is irreversible. Per-platform — happens on each
   target machine after that platform has reached confidence in
   the keyring.

7. **TPM-quote integration in the attestation agent.** The agent
   quotes the PCRs under a restricted attestation key (tactiq-attest
   DDR-004). Remaining: register that key against the TPM endorsement
   key, so that the state described in `ATTESTATION.md` section
   "Attestation payload" holds for an outside verifier.

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
