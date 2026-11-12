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

**Lockdown LSM in confidentiality mode.** Lockdown restricts what the
kernel allows even to the root user: module loading, kexec, direct
hardware access, kernel memory inspection. The mode is set on the
kernel command line, `lockdown=confidentiality`, in the `/chosen`
bootargs of each slot device tree inside the signed FIT
(`tactiq-slot-dtb.bb`), so it is covered by the FIT signature and by
the PCR 1 measurement of the FIT. Confidentiality mode blocks both
modification and reads of kernel memory.

Until 2026-11-10 the kernel configuration carried
`CONFIG_LOCK_DOWN_KERNEL_FORCE_NONE=y` and the command line set no
mode: lockdown was built in and enforced nothing. Earlier text here
said integrity mode; that was wrong. Board measurement:
`measurements/lockdown-userns-board-20261110.md`.

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

IMA appraisal is enforced on the development image.
`CONFIG_IMA_APPRAISE=y` enables the kernel machinery, and the
development image deploys the on-disk policy
(`recipes-security/ima-policy/files/tactiq-ima-appraise.policy`,
installed as `/etc/ima/ima-policy`) with its rootfs signed at build
time. Its command line carries no `ima_appraise=` argument. With
`CONFIG_IMA_APPRAISE_BOOTPARAM=y` and no argument the kernel keeps its
default, enforce (`ima_appraise = IMA_APPRAISE_ENFORCE` in
`security/integrity/ima/ima_main.c`), so a failed appraisal blocks the
access. The argument used to come from a `tactiq-dev-policy` override
in `local.conf`, outside the tree; the override was removed (see
`tactiq-rockchip-rk3588.inc`), and since then the image carries no
argument and enforces.

What is appraised: execution and executable mappings on every
filesystem but the pseudo filesystems the policy names, and reads of
`tactiq_vault_data_t`, which after the label split covers delivered
artifacts alone: device identity and the agent envelopes carry types
of their own and are not appraised. Each appraised access requires a
signature (`appraise_type=imasig`); a digest in `security.ima` is
refused. Reads from tmpfs and ramfs are exempt; execution from them is
not.
Anything delivered onto `/data/tactiq` must arrive with a signature in
`security.ima`.

What enforcement shows on this image: the development signer is
public by design (`pki/README.md`), so anyone can sign a file the
image accepts. Enforcement here shows that the policy and the signed
rootfs work together; keeping out a file signed by someone else needs
a production signer. The record is `measurements/ima-imasig-board-20261109.md`.

A production image is unaffected by any of the above: it applies
neither the signing class nor an appraise rule. From the next release
after v2.1.0-rc14 it loads the measure rules of this policy alone
(`tactiq-ima-measure.policy`, kept equal to them by
`tests/ima/test_ima_policies.py`); not yet observed on a board under the
release key.

`CONFIG_IMA_APPRAISE_MODSIG=y`, which extends IMA appraisal to
kernel module signatures, is not yet enabled. It is a Phase 3
transition that follows the on-disk IMA policy deployment.

## Module signing

Kernel module signing is in place: `CONFIG_MODULE_SIG=y`,
`CONFIG_MODULE_SIG_SHA256=y`, and unsigned modules are refused.
Enforcement is `module.sig_enforce=1` on the kernel command line, in the
same signed bootargs as the lockdown mode; lockdown refuses unsigned
modules as well. `CONFIG_MODULE_SIG_FORCE` stays unset, so the kernel
configuration does not decide enforcement and the signed command line
does.

## Entry points for unprivileged kernel exploits

`CONFIG_USER_NS` is unset. User namespaces let an unprivileged process
hold capabilities inside a namespace, which is the usual way such a
process reaches kernel code paths otherwise closed to it. systemd
sandboxing does not need them: PID 1 creates mount, PID and network
namespaces as root, and no unit in the image uses `PrivateUsers=`.

io_uring is refused to every process by
`sysctl.kernel.io_uring_disabled=2` on the signed kernel command line.
`CONFIG_IO_URING` is only settable with `CONFIG_EXPERT`, so the code is
built in and refused at runtime rather than compiled out; the
`# CONFIG_IO_URING is not set` line in `tactiq-security.cfg` has no
effect. No component of the image uses io_uring.

`CONFIG_USERFAULTFD` and `CONFIG_KEXEC` are unset, and unprivileged BPF
is off by default (`CONFIG_BPF_UNPRIV_DEFAULT_OFF=y`).
`CONFIG_BPF_SYSCALL` stays enabled: systemd uses BPF for the
`IPAddressDeny=` of the agent unit.

None of this stops a kernel exploit once code runs in the kernel; it
narrows how an unprivileged process gets there.

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

The kernel command line is the `/chosen` `bootargs` of each slot device
tree, written by `tactiq-slot-dtb.bb`. The device trees travel inside
the signed FIT that U-Boot verifies before it boots the kernel
(`BOOT_CHAIN.md`), and the boot environment sets no `bootargs` variable
(`tactiq-boot-fit.env`). The lockdown mode, module signature
enforcement and the io_uring refusal described above are therefore
covered by the FIT signature. A command line typed at a U-Boot console
replaces the signed one and gives a PCR 1 that matches no reference;
U-Boot is built without a console unless `TACTIQ_UBOOT_CONSOLE = "1"`.

## Phase 3 transitions

The kernel security fragment marks several configurations as
"Phase 3" in its inline comments. These are the transitions that
move the posture from current to enforcing:

- `CONFIG_IMA_APPRAISE_MODSIG=y` — IMA appraisal extends to kernel
  module signatures.

Module signature enforcement and lockdown confidentiality mode were
Phase 3 items; since 2026-11-10 both are set on the signed kernel
command line (see above).

The transitions are gated on the userspace prerequisites being in
place: a deployed module-signing keyring on production machines, an
on-disk IMA appraisal policy covering the protected paths, an IMA
signing key issued for the target trust hierarchy, and integration
testing of the confidentiality-mode kernel against the runtime
workload set.

`gen-pki.sh` does not issue an IMA signing key today (see
`pki/README.md`). Whoever deploys the appraisal policy must add that
branch to the script in the same change, or the key that signs the
rootfs will have no recorded provenance.

The transitions happen per-machine as each platform completes the
prerequisites; there is no single global Phase 3 cutover date.

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
