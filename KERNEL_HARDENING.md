# Kernel hardening posture

This document describes the kernel hardening posture as configured
in TactiQ OS — what is enabled, what choices the project has made
about the security primitives the Linux kernel offers, and what is
deferred for future phases. It sits alongside `DESIGN_PRINCIPLES.md`
(per-domain rationale), `THREAT_MODEL.md` (consolidated adversary
model), `ATTESTATION.md` (attestation framework), `SUPPLY_CHAIN.md`
(supply-chain self-assessment), `SECURITY.md` (vulnerability
disclosure policy), and `VERIFY.md` (consumer verification
procedure).

This is a v0.1 document. It iterates as the posture evolves through
the phases described below.

Last reviewed: 2026-04-25.

## Status

The kernel security fragment lives at
`recipes-kernel/linux/linux-yocto/tactiq-security.cfg` and is applied
on top of the kernel defconfig for each machine. The fragment is
applied uniformly across all supported `MACHINE` configurations through
a pair of bbappends:

- `recipes-kernel/linux/linux-yocto_%.bbappend` for machines using the
  upstream `linux-yocto` recipe (rock5a, rock5t, generic-arm64,
  qemu-x86).
- `recipes-kernel/linux/linux-rockchip_%.bbappend` for the rock5b
  machine, which uses the `linux-rockchip` recipe from meta-rockchip.

Both bbappends point at the same fragment file, so the posture
described here is the same posture across every supported target.
The CI distro-config-sanity job enforces that every kernel provider
referenced by a tactiq machine.conf has a corresponding bbappend that
pulls the fragment in.

This document is the rationale layer. It explains the choices the
project has made, not the line-by-line meaning of each kernel
config option — the kernel's own documentation is the authoritative
source for what each option does. What is in scope here is why the
TactiQ OS posture looks the way it does and where it is going next.

## LSM choices

TactiQ OS ships SELinux as the primary Mandatory Access Control
mechanism, with the kernel lockdown LSM stacked on top. The
configuration sets `CONFIG_DEFAULT_SECURITY_SELINUX=y` so SELinux is
active from boot, and `CONFIG_SECURITY_LOCKDOWN_LSM_EARLY=y` so
lockdown applies before init.

**Why SELinux as the MAC layer.** SELinux uses type enforcement: the
security context is a label attached to the file or process, not a
function of its filesystem path. This makes the policy robust
against path manipulation and easier to reason about for a system
that ships a known set of daemons in known domains. The
`refpolicy-targeted` reference policy is mature, widely deployed,
and integrates with the IMA hooks that TactiQ OS uses for
attestation. The TactiQ-specific domains
(`tactiq_agent_t`, `tactiq_vault_t`, `tactiq_tpm_t`, `tactiq_rauc_t`,
`tactiq_ctl_t`, `tactiq_tamper_t`, `tactiq_verifier_t`,
`tactiq_fixes_t`) are added as modules on top of the reference
policy. `meta-tactiq-selinux` is the layer that ships them.

**Targeted, not MCS or MLS.** The policy runs in `targeted` mode —
type enforcement only, without Multi-Category Security or
Multi-Level Security overlays. The TactiQ OS deployment model is
single-tenant: one device, one set of services, one operator. MCS
becomes meaningful when multiple workloads with different sensitivity
labels share a host; that is not the current shape. If a future
deployment introduces multi-tenant scenarios, the policy will be
extended.

**Lockdown LSM in integrity mode.** Lockdown restricts what the
kernel allows even to the root user — module loading, kexec, direct
hardware access, kernel memory inspection. The current configuration
runs lockdown in integrity mode, which blocks modifications that
could compromise the running kernel. Confidentiality mode, which
additionally blocks reads of kernel memory and is the relevant
posture against key-extraction attacks, is a Phase 3 transition (see
below).

**LSMs not currently in the stack.** Landlock and BPF-LSM are not
currently in the LSM stack. The current SELinux + lockdown
configuration covers the runtime model the project is designed for.
Adding additional LSM layers will be evaluated as use cases drive
specific requirements; this is a posture choice rather than a
permanent exclusion.

## IMA posture

The Integrity Measurement Architecture is enabled at the kernel
level: `CONFIG_IMA=y`, `CONFIG_IMA_APPRAISE=y`,
`CONFIG_IMA_MEASURE_PCR_IDX=10`, `CONFIG_IMA_LSM_RULES=y`. PCR 10 is
the standard register for IMA runtime measurements; choosing it puts
the TactiQ OS measurement chain in the position remote verifiers
expect.

What this means at the current state: the kernel measures files as
they are accessed and extends those measurements into PCR 10. A
remote verifier, once the attestation framework is fully
implemented, can ask for a TPM quote over PCR 10 and validate that
the running set of measured files matches an expected reference.

What this does not yet mean: IMA appraisal in userspace is not yet
enforced. `CONFIG_IMA_APPRAISE=y` enables the kernel machinery; the
on-disk policy that tells the kernel which files require valid
signatures and what to do when verification fails is not currently
deployed. With kernel machinery present and policy absent, IMA
measures but does not block. The transition to enforcing IMA
appraisal — and the deployment of an on-disk policy covering
`/opt/tactiq/` and the `tactiq-*` systemd unit files — is a Phase 3
item alongside the agent implementation.

`CONFIG_IMA_APPRAISE_MODSIG=y`, which extends IMA appraisal to
kernel module signatures, is not yet enabled. It is a Phase 3
transition that follows the on-disk IMA policy deployment.

## Module signing

Kernel module signing infrastructure is in place:
`CONFIG_MODULE_SIG=y`, `CONFIG_MODULE_SIG_SHA256=y`. This means the
kernel knows how to verify module signatures. It does not yet mean
that unsigned modules are rejected — that requires
`CONFIG_MODULE_SIG_FORCE=y`, which is a Phase 3 transition.

The current behavior: signed modules verify successfully, unsigned
modules load with a kernel warning. Under Phase 3 force mode,
unsigned modules will be refused. The transition is gated on a
deployed signing keyring on production machines and validation that
all modules the runtime requires are signed by that keyring.

## Memory and execution hardening

The configuration enables the standard set of memory-safety
protections: `STACKPROTECTOR_STRONG`, `FORTIFY_SOURCE`,
`HARDENED_USERCOPY`, `SLAB_FREELIST_HARDENED`,
`SLAB_FREELIST_RANDOM`, `SHUFFLE_PAGE_ALLOCATOR`. KASLR is on
through `RANDOMIZE_BASE` and `RANDOMIZE_MEMORY`.

These are not project-specific choices — they are the contemporary
baseline for any security-hardened Linux kernel. The reason they
are listed explicitly here is that "modern kernel hardening
defaults" is not something the audience can take for granted from a
defconfig; the security fragment makes them explicit and the
`tactiq-security.cfg` file is the canonical place where the posture
is recorded.

The configuration also restricts what the root user can inspect
about the running kernel: `STRICT_DEVMEM=y`, `IO_STRICT_DEVMEM=y`,
`SECURITY_DMESG_RESTRICT=y`, `PROC_KCORE=n`. `KEXEC=n` prevents
kernel replacement at runtime — a TactiQ OS device boots into one
kernel and stays in it for the life of the boot. This narrows the
local privileged adversary class described in `THREAT_MODEL.md`.

## Compiler hardening

Compiler hardening is applied at the distribution level rather than
in the kernel fragment. `conf/distro/tactiq.conf` sets
`SECURITY_CFLAGS = "-fstack-protector-strong -D_FORTIFY_SOURCE=2"`
and `SECURITY_LDFLAGS = "-Wl,-z,relro,-z,now"`, which are appended
to `TARGET_CFLAGS` and `TARGET_LDFLAGS` for every package the build
produces. PIE is the default position-independent executable mode
inherited from poky.

The combination produces userspace binaries with stack canaries,
runtime overflow checks where the compiler can detect them, full
RELRO with immediate binding (so the GOT is read-only at runtime),
and ASLR-effective relocation. These are project-wide rather than
opt-in per recipe.

## Attack surface reduction

The image is built to remove what the runtime does not need rather
than to ship a default desktop or server profile and turn things
off. `conf/distro/tactiq.conf` removes the following distro features
explicitly: `x11`, `wayland`, `vulkan`, `opengl`, `pulseaudio`,
`bluetooth`, `nfc`, `3g`, `alsa`, `wifi`, `zeroconf`, `nfs`,
`pcmcia`, `pci`, `gobject-introspection-data`. Each removal closes
out a class of code that would otherwise be in the image and would
be reachable from somewhere.

This is a posture choice — TactiQ OS targets edge AI deployments
where the runtime workload is well-defined. A general-purpose
embedded distribution would make different choices.

## Initramfs

Initramfs composition, signing posture, and integration with the
boot chain are not currently documented as a stand-alone artifact.
The initramfs is generated by the Yocto build and consumed by the
bootloader as part of the kernel image; full documentation of its
composition and how it integrates with the verified boot chain is
an acknowledged gap, to be closed alongside FIT image signing work
tracked in the boot chain area.

This is called out explicitly because the initramfs is a known weak
shoulder in any Linux verified boot chain — without an explicit
account of what is in it and how it is verified, the chain of
measurement that follows it is built on an undocumented foundation.
The gap is not yet closed; it is named so that it is not invisible.

## Kernel command line

Kernel command-line parameters are passed by the bootloader to the
kernel at boot. Until FIT image signing is in place (tracked in the
boot chain area), command-line parameters travel through an
unsigned bootloader and are therefore modifiable by anyone who can
write to the boot media. Once FIT signing is implemented,
command-line parameters become part of the signed FIT payload and
are protected against modification along with the kernel image
itself.

This is mentioned because the kernel command line is part of the
chain of trust, not a separate concern — and the current state is
that this part of the chain is not yet anchored.

## Phase 3 transitions

The kernel security fragment marks several configurations as
"Phase 3" in its inline comments. These are the transitions that
move the posture from current to enforcing:

- `CONFIG_MODULE_SIG_FORCE=y` — unsigned kernel modules are rejected
  at load time, not only warned about.
- `CONFIG_IMA_APPRAISE_MODSIG=y` — IMA appraisal extends to kernel
  module signatures.
- `CONFIG_LOCK_DOWN_KERNEL_FORCE_CONFIDENTIALITY=y` — lockdown moves
  from integrity mode to confidentiality mode, additionally
  blocking reads of kernel memory.

The transitions are gated on the userspace prerequisites being in
place: a deployed module-signing keyring on production machines, an
on-disk IMA appraisal policy covering the protected paths, and
integration testing of the confidentiality-mode kernel against the
runtime workload set. The transitions happen per-machine as each
platform completes the prerequisites; there is no single global
Phase 3 cutover date.

## What this hardening does not cover

The kernel hardening posture is one layer in a chain. It assumes
properties it does not itself provide:

- **An anchored boot chain.** The hardening described here is
  meaningful only if the kernel that boots is the kernel that was
  built and signed. Until the boot chain is anchored at a hardware
  root of trust (RK3588 OTP fuses burned, FIT image signing
  implemented), an attacker with write access to boot media can
  install a kernel without these protections, and none of the
  kernel-level controls applies. This is tracked in the boot chain
  area.
- **A discrete TPM.** On platforms where the TPM is firmware-rooted
  in the SoC's secure-world TEE rather than a discrete chip, the
  strength of the cryptographic root that some of these protections
  depend on is bounded by TEE isolation. See `THREAT_MODEL.md`
  section 6 for per-platform variation.
- **Workload-level integrity.** Kernel hardening defends the kernel
  and the userspace processes the kernel runs. It does not attest
  what those processes do at runtime — model authenticity,
  inference correctness, data handling are application-layer
  concerns.
- **Side-channel and silicon-level attacks.** Out of scope for the
  current generation of supported hardware; see `THREAT_MODEL.md`.

## References

- `THREAT_MODEL.md` — consolidated adversary model.
- `ATTESTATION.md` — attestation framework specification.
- `DESIGN_PRINCIPLES.md` — per-domain rationale.
- `SUPPLY_CHAIN.md` — supply-chain self-assessment and roadmap.
- `recipes-kernel/linux/linux-yocto/tactiq-security.cfg` — kernel
  security fragment.
- `conf/distro/tactiq.conf` — distro-level CFLAGS, LDFLAGS, distro
  feature additions and removals.
- `meta-tactiq-selinux` — SELinux policy modules layered on top of
  `refpolicy-targeted`.
