# Threat model

This document is the consolidated adversary model for TactiQ OS. It
describes what the operating system layer is designed to protect, against
which classes of adversary, and where the trust boundaries are drawn. It
sits alongside `DESIGN_PRINCIPLES.md` (per-domain rationale),
`ATTESTATION.md` (architectural specification of the attestation
framework), `SUPPLY_CHAIN.md` (supply-chain self-assessment),
`SECURITY.md` (vulnerability disclosure policy), and `VERIFY.md`
(consumer verification procedure).

This is a v0.1 document. It is the first consolidated articulation of the
adversary model and it will iterate as the platform matures, as
per-machine bring-up completes, and as community review surfaces gaps.

Last reviewed: 2026-04-25.

## Scope and stance

This threat model describes TactiQ OS as a distribution. It is
hardware-agnostic by design and applies across all supported `MACHINE`
configurations. The architectural model is the same for every target;
what varies between targets is the strength of the hardware primitives
that anchor each part of the model. The per-platform variations are
covered in section 6 and tracked in detail in `docs/machines/` as each
platform completes bring-up.

The model is written from the perspective of an operating system layer
deployed in environments where cloud dependency is not an option:
offline-first runtime, sovereign data control, no reliance on external
PKI or external attestation services. The threat model reflects those
conditions.

This is not a formal threat modeling exercise (STRIDE matrix per asset,
external review by a third-party security firm, compliance mapping to a
specific framework). Those are work that becomes meaningful when the
platform reaches production deployments with concrete customer
requirements. At the current stage the goal is a clear, honest, public
articulation of what TactiQ OS is designed to defend against and what it
is not.

## Assets

TactiQ OS is designed to protect four categories of assets.

**Data on the device.** Captured frames, sensor readings, audit logs,
locally trained or deployed model weights, runtime state, configuration,
cryptographic key material. The principle is that data generated or
stored on the device should remain physically and cryptographically
controlled by the device's legitimate operator, with no leakage path
to external parties absent explicit operator consent.

**Runtime integrity.** The property that the code executing on the
device is the code that was built, signed, and installed through a
verifiable supply chain. This is what the boot-and-runtime-integrity
machinery (read-only rootfs, RAUC A/B signed updates, kernel hardening,
IMA, lockdown, module signing) is designed to enforce.

**Verifiability.** The property that the device can prove its current
state to a remote party with whom it has a pre-established trust
relationship. This is what the attestation framework is designed to
support.

**Sovereign control.** The property that legal and operational control
over the device's data and runtime resides with the operator's
jurisdiction, not with a foreign cloud provider, certificate authority,
or update server. This is a positioning property as much as a technical
one — it constrains design choices (no mandatory cloud connectivity, no
foreign PKI dependencies, no telemetry).

## Adversary classes

Six classes of adversary are considered. For each, capabilities and
current mitigations are described as they exist in the present
codebase. Items not yet implemented are marked explicitly.

### Network attacker

**Capabilities.** Passive observation and active manipulation of
traffic between the device and any remote endpoint it communicates
with — verifier, update server, telemetry consumer (where present).
No physical access to the device. May be on-path or off-path.

**Current mitigations.** mTLS 1.3 is specified as the transport for
agent-to-verifier communication; client and server authentication via
certificates. RAUC update bundles are signature-verified before
installation, so a network attacker who modifies a bundle in flight
cannot cause unauthorized code to run.

**Known gaps at this stage.** The attestation agent currently shipped
is a stub (`recipes-core/tactiq-agent/files/tactiq-agent-stub.sh`); the
mTLS path described in `DESIGN_PRINCIPLES.md` is the design target, not
a running implementation. Anti-rollback on RAUC bundles
(generation counter) is not yet wired. Update bundle delivery channel
authenticity beyond signature verification (e.g. authenticated transport
to a known update endpoint) is per-deployment configuration, not
distro-level enforcement.

### Local non-privileged user

**Capabilities.** Has credentials of an unprivileged user account on
the device. Can run user-level processes, read user-readable files,
attempt local privilege escalation through kernel or setuid binary
exploits.

**Current mitigations.** Read-only rootfs limits persistence of
modifications even after privilege escalation. SELinux confinement
prevents lateral movement between domains. Kernel hardening
(`STACKPROTECTOR_STRONG`, `FORTIFY_SOURCE`, `HARDENED_USERCOPY`,
`SLAB_FREELIST_HARDENED`, `RANDOMIZE_BASE`) raises the cost of kernel
exploitation. Compiler hardening (`relro`, `bind-now`, PIE,
`_FORTIFY_SOURCE=2`) applied across the userspace.

**Known gaps at this stage.** The development image profile retains
`debug-tweaks` in `EXTRA_IMAGE_FEATURES` (explicitly marked "CHANGE IN
PRODUCTION" in the image recipe), which loosens default user posture.
The production profile that removes this is tracked but not yet a
separate published artifact. Kernel module signing is enabled
(`CONFIG_MODULE_SIG=y`) but not enforced (`CONFIG_MODULE_SIG_FORCE` is
phase-3 work in `tactiq-security.cfg`).

### Compromised userspace daemon

**Capabilities.** Code execution within the address space of a
specific daemon, obtained through exploitation of a parsing,
deserialization, or memory-safety vulnerability. Has the privileges and
filesystem access granted to that daemon by SELinux policy.

**Current mitigations.** SELinux type enforcement is the primary
boundary. Each TactiQ daemon (`tactiq_agent`, `tactiq_vault`,
`tactiq_tpm`, `tactiq_rauc`, `tactiq_verifier`, `tactiq_ctl`,
`tactiq_tamper`, `tactiq_fixes`) runs in its own domain with explicit
allow rules; default deny otherwise. Domain transitions enforced by
`init_daemon_domain`. Seccomp filtering available at the syscall
boundary. Audit subsystem captures policy violations.

**Known gaps at this stage.** Per-daemon seccomp profiles are not yet
shipped — the kernel machinery is enabled but per-daemon syscall
filters are deployment-time work. The `meta-tactiq-selinux` policy
repository does not yet ship under the same signed-release regime as
`meta-tactiq` itself, so a consumer cannot today independently verify
that the binary policy on the device traces back to a signed source
tag in the policy repository. Bringing the policy repository under the
same signing, verification, and reproducibility discipline is the
first post-rc3 supply-chain task.

### Local privileged / root user

**Capabilities.** Has unrestricted userspace privileges. Can read and
write any file the kernel permits, load modules (subject to module
signing posture), read kernel memory (subject to lockdown posture),
arbitrary network operations.

**Current mitigations.** Kernel lockdown LSM enabled at boot
(`CONFIG_SECURITY_LOCKDOWN_LSM_EARLY=y`) restricts what root can do
against the kernel. `CONFIG_STRICT_DEVMEM`, `CONFIG_IO_STRICT_DEVMEM`,
`CONFIG_PROC_KCORE=n`, `CONFIG_SECURITY_DMESG_RESTRICT` constrain root
access to kernel internals. `CONFIG_KEXEC=n` prevents kernel
replacement at runtime. SELinux, with `selinux=1 enforcing=1` as the
default policy, applies even to the root user — root is not a SELinux
bypass.

**Known gaps at this stage.** Lockdown is in integrity mode in rc3;
confidentiality mode (`CONFIG_LOCK_DOWN_KERNEL_FORCE_CONFIDENTIALITY=y`),
which additionally blocks kernel memory reads and is relevant against
key extraction, is phase-3 work. IMA appraisal at the kernel level is
configured (`CONFIG_IMA_APPRAISE=y`, PCR 10), but on-disk appraisal
policy covering `/opt/tactiq/` and the tactiq systemd units is not
yet deployed; without on-disk policy, IMA measures but does not
enforce on file access.

### Physical attacker

The physical attacker class is split into two subclasses, because
mitigations and threat scope differ substantially.

**Opportunistic physical attacker.** Has temporary or permanent
physical possession of the device — stolen, captured, abandoned. Has
common tooling: SD card readers, USB-UART, JTAG probes if interfaces
are exposed, capacity to read or write eMMC and SD storage. Does not
have access to a chip-level laboratory.

*Mitigations applicable.* Read-only rootfs + signed RAUC means a
modified rootfs written back to storage cannot boot in a verifying
chain (once the verifying chain itself is wired — see below). TPM-sealed
keys, when implemented, prevent extraction of cryptographic material
without the original platform state. SELinux and lockdown still apply
if the attacker can boot the device.

*Known gaps at this stage.* The verifying boot chain is the central
unsigned link in rc3: RK3588 OTP fuses are not burned, FIT image
signing is not implemented, the bootloader is not anchored. An
opportunistic physical attacker who can flash storage can today boot
the device into an unverified state. Sealing keys to the TPM and
binding them to expected PCR values mitigates the data-extraction half
of this attacker; the runtime-integrity half depends on the
end-to-end signed boot chain reaching production state.

**Well-resourced physical attacker.** Has access to chip-level
laboratory: decapsulation, side-channel analysis rigs, fault injection
equipment, focused ion beam. Capable of attacking SoC ROM, RAM, and
cryptographic operations at the silicon level.

*Stance.* TactiQ OS does not claim defense against this class for the
current generation of supported hardware. The reference SoC families
(RK3588 family, MediaTek Genio family, generic ARM64) are commercial
parts without certified physical attack resistance to this level.
Defense at this level is a hardware design problem; it is mentioned
here so that consumers of TactiQ OS understand the bound. For
deployment scenarios where this attacker is in scope, hardware
selection and physical security around the device are the
appropriate mitigations, not OS-layer hardening.

### Supply chain attacker

**Capabilities.** Compromise of any element of the chain that produces
the device's running software: the build host, the developer
workstation, an upstream dependency, the keying material used to sign
release artifacts, the CI identity used to authorize signing
workflows.

**Current mitigations.** SPDX 3.0 SBOM produced per build (wrynose
removed SPDX 2.2; rc2/rc3 shipped SPDX 2.2 with 763 packages, 7,178
files at 100% SHA-256 coverage — rc5 figures pending re-measurement).
CVE scanning via `sbom-cve-check` against the NIST NVD feed every
build. SLSA
v1.0 build-provenance attestation on the tagged source archive for
`v2.1.0-rc3` via `actions/attest-build-provenance` and Sigstore OIDC
keyless signing, generated by a workflow identity rather than a
personal account, recorded on the public Rekor transparency log
(consumer-side status of the attestation file is in
[`VERIFY.md`](VERIFY.md) §5). Per-file content reproducibility verified
at 99.943% byte-identity on `rootfs.ext4` between independent builds.
Kernel pinned to a specific LTS point-release series. Source archiver
retains upstream tarballs.

**Known gaps at this stage.** SLSA L3 on the rootfs image itself
requires a hosted hermetic builder; the current image build is local
(WSL2 + Docker). Two-independent-builds bit-for-bit diff is not yet a
required CI gate. Filesystem-image bit-identity (vs per-file content
identity) requires elimination of remaining non-deterministic sources
in `do_image_ext4`. Production RAUC keyring rotation from in-tree
development root (`pki/dev/root-ca.pem`) to CI-secret-provisioned
keyring is tracked. FIT image signing is not implemented. Full
roadmap in `SUPPLY_CHAIN.md`.

## Trusted Computing Base

The TCB of TactiQ OS is the set of components whose compromise
invalidates the security guarantees of the platform. It is drawn at
the smallest scope that is consistent with the present
implementation.

**In TCB.**

- SoC boot ROM and any immutable hardware roots of trust on the
  selected platform.
- Bootloader and FIT image (once signed; see boot chain status).
- Kernel image and initramfs (once signed and measured into the TPM;
  see boot chain status).
- TPM (discrete or firmware), with the caveat that the strength of
  the root depends on TPM class — see section 6.
- SELinux binary policy as deployed on the device.
- The release-signing keyring and the workflow identity authorized to
  produce signed releases.
- The RAUC update keyring as deployed on the device.

**Not in TCB.**

- Userland services running under SELinux confinement. They are
  protected, but their compromise is bounded by their domain rather
  than catastrophic to the platform.
- Workload models executing on the NPU or other accelerators. Model
  compromise is an application-layer concern.
- Network endpoints the device communicates with, including update
  servers and verifiers. mTLS provides authenticated and confidential
  channels; the endpoints themselves are out of TCB scope.
- USB-attached peripherals at any time, including during development.
- The physical environment of the device.

The TCB will shrink as more of the boot chain is brought into a
verified state. It will not grow.

## Attestation declaration vs. measurement boundary

This is called out as a separate item rather than folded into one of
the adversary classes because it is the most consequential current
limitation and a consumer of this document needs to understand it
explicitly.

The attestation agent is a stub. When the agent is
brought to a real implementation, the design target is for it to
include a TPM quote in its signed payload, so that what the device
attests is what the hardware measured at boot. Until that integration
lands, an attestation produced by the agent attests to what userspace
declares about the device, not to what the hardware measured. This is
the difference between "the agent signs" and "the system proves what
it ran." TactiQ OS is in the first state and is
designed to reach the second.

A consumer of attestation produced by TactiQ OS today should treat
the attestation as build-identity self-declaration of the running
userspace, anchored by the agent's signing key. A consumer of
attestation post-TPM-quote integration can treat it as a
hardware-measured statement of platform state.

This boundary is the central reason why production deployment of
TactiQ OS in trust-critical scenarios is a future state, not a
present one.

The full architectural specification of the attestation framework —
what is signed, freshness, replay defence, verification protocol,
key management, and the implementation roadmap from the current
stub state — is in [`ATTESTATION.md`](ATTESTATION.md).

## Per-platform variations

The architectural threat model above applies uniformly across all
supported `MACHINE` configurations. What varies between platforms is
the strength of the hardware primitives that anchor each part:

- **Class of TPM available.** A discrete TPM 2.0 chip provides a
  hardware-rooted attestation primitive that is independent of the
  main SoC. A firmware TPM (fTPM) implemented in the SoC's secure
  world (TrustZone TEE on ARM, equivalent on x86) provides a
  software-rooted primitive whose strength derives from the TEE's
  isolation guarantees. The threat model parameters are not the same.
- **Hardware-anchored secure boot.** Whether the SoC's boot ROM
  cryptographically verifies the next stage against an OTP-fused
  public key root depends on whether the OTP fuses have been burned
  for that target. Until they are, the chain of trust starts at an
  unverified bootloader.
- **Verified boot chain implementation status.** Whether FIT image
  signing, kernel module signature enforcement, and IMA appraisal
  policy are deployed varies per machine and per release.

The supported machine configurations and their current state along
these axes are tracked in `docs/machines/` as each platform completes
bring-up. At the time of this writing the qemu-x86 machine is the
only validated functional CI target; the physical Rockchip-family
machines (rock5a, rock5b, rock5t) are in active bring-up phase, with
fTPM as the available TPM class on the reference hardware and the
secure boot anchor not yet activated. The generic-arm64 machine is a
template configuration whose state depends on the target board.

`docs/machines/` is the canonical source for current per-platform
status. This threat model describes the model into which each
platform integrates as it matures.

## What this threat model does not cover

The following are explicitly outside the scope of this v0.1 model.
They may be added in subsequent revisions when implementation, use
cases, or consumer requirements warrant.

**Coercion-resistant operations and operator-side adversary
scenarios.** Duress codes, dead-man switches, cascading data
destruction, scenarios where a legitimate device holder is compelled
to operate it under adversary control. Tracked as future work tied to
specific deployment requirements; not part of the current generic
adversary model.

**Coordinated multi-party collusion.** Scenarios where multiple
nominally-independent actors in the supply chain, deployment, or
verification path act in concert against the platform's intended
beneficiary. This is a governance and contractual problem, not one
that operating-system controls can solve.

**Side-channel and fault injection at the silicon level.** Out of
scope for the current generation of supported hardware (see physical
attacker class). Tracked as a hardware-selection consideration rather
than an OS-layer mitigation target.

**Compliance mapping.** This document does not map adversary classes
or mitigations to NIST 800-53, ISO 27001, IEC 62443, or other
compliance frameworks. Compliance work becomes meaningful when there
is a specific deployment with a specific compliance target; at the
current stage it would be premature.

**Formal verification of the policy or the kernel.** Static analysis
of SELinux policy beyond syntax checks, formal proofs of kernel
properties, or model checking of the attestation protocol are not
part of the current state and are not on the near-term roadmap.

## References

- `DESIGN_PRINCIPLES.md` — per-domain rationale and current state.
- `ATTESTATION.md` — architectural specification of the attestation
  framework.
- `SUPPLY_CHAIN.md` — supply-chain self-assessment and roadmap.
- `SECURITY.md` — vulnerability disclosure policy.
- `VERIFY.md` — consumer verification procedure.
- `docs/release-notes/v2.1.0-rc7.md` — current release notes and known
  limitations.
- `docs/machines/` — per-platform bring-up status (canonical source for
  per-platform state).
