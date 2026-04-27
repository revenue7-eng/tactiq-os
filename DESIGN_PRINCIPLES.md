# Design principles

This document describes the architectural principles realized in the
meta-tactiq layer at the current release, what is tracked but not yet
shipped, and what is out of scope. It sits alongside `THREAT_MODEL.md`
(consolidated adversary model that motivates the principles below),
`ATTESTATION.md` (architectural specification of the attestation
framework), `KERNEL_HARDENING.md` (kernel hardening posture and
rationale), `BOOT_CHAIN.md` (chain of trust from silicon root to
running attestation agent), `SUPPLY_CHAIN.md` (supply-chain posture),
`SECURITY.md` (vulnerability policy), and `VERIFY.md` (consumer
verification procedure). Each statement about the current state is
backed by a file in this repository.

Last reviewed: 2026-04-25.

Sections follow the chain of trust from the source archive up to the
runtime attestation agent.

## Supply chain

**Principle.** Every shipped artifact is reproducible, inventoried, and
signed under a non-personal identity.

**Current state.** SPDX 2.2 SBOM per build via `INHERIT += "create-spdx"`
in `recipes-core/images/tactiq-image.bb`; the `v2.1.0-rc2` and
`v2.1.0-rc3` releases ship 895 SPDX documents with a single-file
aggregate of 763 packages and 7,178 files at 100% SHA-256 coverage.
CVE scanning via `INHERIT += "cve-check"` in `conf/distro/tactiq.conf`
emits a JSON manifest against the NIST NVD feed on every build; patched
CVEs are reported rather than hidden (`CVE_CHECK_REPORT_PATCHED = "1"`).
`BUILD_REPRODUCIBLE_BINARIES = "1"` and a pinned `linux-yocto` 6.6 LTS
point-release series produce per-file content reproducibility (99.943%
byte-identity on `rootfs.ext4` between two consecutive builds;
remaining 0.057% localized to ext4 inode metadata and filesystem
headers). Source archiver retains upstream tarballs. A cosign keyless
signature over `SHA256SUMS` transitively covers every release artifact;
`v2.1.0-rc3` was signed under the workflow identity of
`.github/workflows/release-sign.yml` running on GitHub Actions at the
time of tagging — not under a personal account — and the signing path
for releases produced after `rc3` is documented in the release notes
of each such release. A SLSA v1.0 build-provenance attestation over
the deterministic source archive was produced by the same workflow
runtime and is recorded on the public Sigstore Rekor transparency log;
the consumer-side status of that attestation file is in
[`VERIFY.md`](VERIFY.md) §5.

**Tracked.** Filesystem-image bit-identity (pending `mkfs.ext4 --uuid`
pinning, inode-timestamp normalization, deterministic `machine-id` and
`random-seed`). Hosted image build as a prerequisite for SLSA L3 on the
rootfs itself. Two-independent-builds diff as a CI gate. Full roadmap
in `SUPPLY_CHAIN.md`.

## Hardware root of trust

**Principle.** Cryptographic operations are bound to hardware identity,
not to software-held secrets.

**Current state.** TPM 2.0 enabled as a distro feature in
`conf/distro/tactiq.conf`; kernel TPM drivers compiled in
(`CONFIG_TCG_TPM`, `CONFIG_TCG_TIS`, `CONFIG_TCG_TIS_SPI`,
`CONFIG_TCG_TIS_I2C`, `CONFIG_TCG_CRB`, `CONFIG_HW_RANDOM_TPM` in
`recipes-kernel/linux/linux-yocto/tactiq-security.cfg`). The attestation
agent at `/opt/tactiq/bin/tactiq-agent` uses Ed25519 for signing
(`recipes-core/tactiq-agent/`). RAUC A/B updates are signed; the current
tree ships a development keyring (`development-1.cert.pem`) for
reproducibility of the development path.

**Tracked.** Production RAUC keyring rotation from the in-tree
development certificate to a keyring provisioned from CI secrets at
build time. RK3588 OTP-fused secure-boot root. FIT image signing.
TPM-quote integration into the attestation agent. All tracked in
`SUPPLY_CHAIN.md`.

## Boot and runtime integrity

**Principle.** The system that is running is the system that was built
and signed.

**Current state.** Read-only rootfs via `IMAGE_FEATURES +=
"read-only-rootfs"` in `recipes-core/images/tactiq-image.bb`. RAUC A/B
signed updates (`recipes-core/rauc/`). Kernel hardening in
`tactiq-security.cfg`: `STACKPROTECTOR_STRONG`, `FORTIFY_SOURCE`,
`HARDENED_USERCOPY`, `SLAB_FREELIST_HARDENED`, `SLAB_FREELIST_RANDOM`,
`SHUFFLE_PAGE_ALLOCATOR`, `RANDOMIZE_BASE`, `RANDOMIZE_MEMORY`. Module
signing with SHA-256 (`CONFIG_MODULE_SIG=y`, `CONFIG_MODULE_SIG_SHA256=y`).
Distro-wide compiler hardening in `conf/distro/tactiq.conf`:
`-fstack-protector-strong`, `_FORTIFY_SOURCE=2`, `relro`, `bind-now`,
PIE. IMA machinery present: `CONFIG_IMA=y`, `CONFIG_IMA_APPRAISE=y`,
`CONFIG_IMA_MEASURE_PCR_IDX=10`, `CONFIG_IMA_LSM_RULES=y`.

**Tracked.** `CONFIG_MODULE_SIG_FORCE=y` and
`CONFIG_IMA_APPRAISE_MODSIG=y` (phase 3 of the security fragment).
On-disk IMA appraisal policy covering `/opt/tactiq/` and
`/usr/lib/systemd/system/tactiq-*`. `dm-verity` on rootfs.
`CONFIG_LOCK_DOWN_KERNEL_FORCE_CONFIDENTIALITY=y` (phase 3).

## Isolation model

**Principle.** Isolation is enforced by mandatory access control, not
by discretionary permissions.

**Current state.** SELinux enforcing as the default LSM
(`CONFIG_DEFAULT_SECURITY_SELINUX=y` in `tactiq-security.cfg`;
`DISTRO_FEATURES` appends `selinux` in `conf/distro/tactiq.conf`).
The targeted reference policy is installed together with the TactiQ
custom modules shipped from the sibling repository
`meta-tactiq-selinux`: `tactiq_agent`, `tactiq_ctl`, `tactiq_fixes`,
`tactiq_rauc`, `tactiq_tamper`, `tactiq_tpm`, `tactiq_vault`,
`tactiq_verifier` (eight `.te`/`.if`/`.fc` triplets). Seccomp syscall
filtering (`CONFIG_SECCOMP`, `CONFIG_SECCOMP_FILTER`). Audit subsystem
enabled (`CONFIG_AUDIT`, `CONFIG_AUDITSYSCALL`). PAM. Namespaces and
cgroups present to support systemd sandboxing primitives
(`CONFIG_USER_NS`, `CONFIG_PID_NS`, `CONFIG_NET_NS`, `CONFIG_CGROUPS`
and subsystems).

**Tracked.** The sibling `meta-tactiq-selinux` repository does not yet
carry the same signed-release regime as this one — no tagged
cosign-signed releases, no `VERIFY.md`, no Rekor-anchored signature
over compiled policy artefacts. A consumer cannot today independently
verify a chain from `rootfs-rock5a.ext4` back to a signed SELinux
policy source tag. Bringing the policy repository under the same
signing, verification, and reproducibility discipline is the first
post-`rc3` supply-chain task (acknowledged in `docs/release-notes/v2.1.0-rc3.md`).

## Attack surface reduction

**Principle.** The image contains what the runtime needs and no more.
A removed feature is a feature that cannot be exploited.

**Current state.** `conf/distro/tactiq.conf` removes the following
distro features by name: `x11`, `wayland`, `vulkan`, `opengl`,
`pulseaudio`, `bluetooth`, `nfc`, `3g`, `alsa`, `wifi`, `zeroconf`,
`nfs`, `pcmcia`, `pci`, `gobject-introspection-data`. The image recipe
pins an explicit minimal `util-linux` subset rather than installing
the full package. Kernel modules are selected individually rather than
pulling the full `kernel-modules` set. `CONFIG_KEXEC=n` disables kernel
replacement at runtime. `CONFIG_STRICT_DEVMEM=y` and
`CONFIG_IO_STRICT_DEVMEM=y` restrict `/dev/mem` and `/dev/port`.
`CONFIG_SECURITY_DMESG_RESTRICT=y` restricts kernel log access.
`CONFIG_PROC_KCORE=n` removes kernel memory dumping. The network
stack is present but scoped to what the attestation and update paths
require (mTLS, RAUC); no user-facing network services are exposed
beyond SSH for maintenance access.

**Tracked.** Production image profile removes `debug-tweaks` from
`EXTRA_IMAGE_FEATURES` and the interactive shell. SSH posture under
the production profile is narrowed to mTLS-only (current state is
`EXTRA_IMAGE_FEATURES:append = " debug-tweaks"` in the image recipe,
explicitly marked as "CHANGE IN PRODUCTION").

## Attestation

**Principle.** The device is able to prove to a remote party what it
is running.

**Current state.** The supporting infrastructure for an attestation
agent is in place: kernel TPM drivers compiled in (see Hardware root
of trust above); IMA machinery enabled at PCR 10; a systemd unit
(`tactiq-agent.service` in `recipes-core/tactiq-agent/files/`); a
SELinux domain (`tactiq_agent_t`) with permissions to access TPM
device nodes through the `tactiq_tpm_access` macro; a vault domain
(`tactiq_vault_t`) for sealed key material; build identity written
into `/etc/tactiq-release` on every image (version, codename, UTC
build date, machine target, meta-layer git short hash, image
basename) by the `tactiq-release` recipe, so that a remote verifier
can correlate a running system with a specific build artifact. The
binary at `/opt/tactiq/bin/tactiq-agent` in v2.1.0-rc3 is a stub
(`recipes-core/tactiq-agent/files/tactiq-agent-stub.sh`) that holds
the systemd unit, SELinux domain, and TPM access primitives in place
while the real implementation is built.

**Tracked.** The full architectural specification of the attestation
framework — payload structure, key management, freshness mechanism,
verification protocol, what attestation does and does not prove — is
in [`ATTESTATION.md`](ATTESTATION.md). The implementation roadmap
from the current stub state to the specification is also there. The
key items: real agent binary (Ed25519 signing with TPM-resident
non-exportable keys, mTLS 1.3 transport); TPM-quote integration that
closes the gap between "the agent signs" and "the system proves what
it ran"; reference verifier implementation; per-build Reference
Integrity Manifest (RIM) generation in the release pipeline.

## Out of scope for the current release

The following are explicitly not claimed by this document or by the
artifacts of the current release:

- Hardware qualification data. Performance, thermal, and sustained-load
  metrics are published per the measurement standard described in
  `README.md` and require the full qualification cycle; they are not
  part of `rc3`.
- SLSA L3 posture on the rootfs image. The current posture is L2 for
  the components built in CI (source archive) and L1 for the full
  rootfs image. L3 requires a hermetic builder, tracked in
  `SUPPLY_CHAIN.md`.
- FIPS 140-3 or Common Criteria certification.
- IMA appraisal enforced in userspace. Kernel machinery is present,
  on-disk policy is not deployed.
- `dm-verity` on rootfs. Tracked in the kernel fragment as phase 3.
- A threat model document. The consolidated adversary model is now
  published in [`THREAT_MODEL.md`](THREAT_MODEL.md). It is a v0.1
  document and iterates as the platform matures.

## References

- `THREAT_MODEL.md` — consolidated adversary model.
- `ATTESTATION.md` — architectural specification of the attestation
  framework.
- `KERNEL_HARDENING.md` — kernel hardening posture and rationale.
- `BOOT_CHAIN.md` — chain of trust from silicon root to attestation.
- `SUPPLY_CHAIN.md` — per-SLSA-requirement self-assessment and roadmap.
- `SECURITY.md` — vulnerability disclosure policy and security hardening
  summary.
- `VERIFY.md` — consumer verification procedure for release artifacts.
- `conf/distro/tactiq.conf` — distro features, security CFLAGS,
  CVE-check configuration.
- `conf/machine/tactiq-*.conf` — per-board machine configurations.
- `recipes-core/images/tactiq-image.bb` — image composition.
- `recipes-kernel/linux/linux-yocto/tactiq-security.cfg` — kernel
  security fragment.
- `recipes-core/tactiq-agent/` — attestation agent recipe.
- `recipes-core/rauc/` — RAUC A/B update configuration.
- `docs/release-notes/v2.1.0-rc3.md` — current release notes and known
  limitations.
