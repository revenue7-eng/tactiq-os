# meta-tactiq

Yocto layer for TactiQ OS — a security-hardened embedded Linux distribution
for edge AI deployments on Rockchip RK3588 and compatible ARM64 targets.

[![ci](https://github.com/revenue7-eng/tactiq-os/actions/workflows/ci.yml/badge.svg)](https://github.com/revenue7-eng/tactiq-os/actions/workflows/ci.yml)

## Scope

- `conf/distro/tactiq.conf` — systemd + SELinux + TPM2 + seccomp + RAUC; hardened CFLAGS; reproducible-binaries flag on; `cve-check` inherited; source archiver on.
- `conf/machine/*` — Rock 5A, Rock 5B, Rock 5T, generic ARM64, qemu-x86_64.
- `recipes-core/images/tactiq-image.bb` — minimal image, read-only rootfs, `create-spdx` inherited (SPDX 2.2 SBOM per build).
- `recipes-core/rauc/` — RAUC A/B update config (development keyring; production signing key rotation tracked separately).
- `recipes-core/tactiq-{agent,config,release}` — attestation agent (Ed25519), runtime config, build info embedded at `/etc/tactiq-release`.
- `recipes-kernel/linux/` — linux-yocto 6.6 LTS pinned, security fragment enabling IMA, SELinux, kernel lockdown groundwork.

## Architectural principles

See [`DESIGN_PRINCIPLES.md`](DESIGN_PRINCIPLES.md) for the per-domain
rationale behind the layer — what the current release realizes, what
is tracked but not yet shipped, and what is out of scope. Organized
by chain of trust from the source archive up to the runtime
attestation agent.

The consolidated adversary model — what TactiQ OS is designed to
defend against, against which classes of adversary, and where the
trust boundaries are drawn — is in [`THREAT_MODEL.md`](THREAT_MODEL.md).

The architectural specification of the attestation framework — what
the device is built to prove to a remote party, the protocol toward
which the agent is being implemented, and what attestation does and
does not prove at the current implementation stage — is in
[`ATTESTATION.md`](ATTESTATION.md).

The kernel hardening posture — LSM choices, IMA configuration,
module signing, memory and execution hardening, and the transitions
that move the posture from current to enforcing — is in
[`KERNEL_HARDENING.md`](KERNEL_HARDENING.md).

The chain of trust from the silicon root to the running attestation
agent — what each stage verifies and measures, where the chain is
anchored, and the state of each stage in the current release — is
in [`BOOT_CHAIN.md`](BOOT_CHAIN.md).

## Supply-chain posture

Self-assessed, not certified. See [`SUPPLY_CHAIN.md`](SUPPLY_CHAIN.md) for the
per-SLSA-requirement breakdown — what is wired today, what is tracked, what
is explicitly not done.

Short version:

| Area                   | State                                                  |
|------------------------|--------------------------------------------------------|
| SBOM                   | SPDX 2.2 per build (Yocto `create-spdx`)               |
| CVE scan               | `cve-check` inherited — JSON report per build          |
| Reproducible builds    | `BUILD_REPRODUCIBLE_BINARIES=1`, kernel version pinned |
| Build provenance       | Signed SLSA provenance on tagged source archives via `actions/attest-build-provenance` (Sigstore) |
| Source archive         | Yocto `archiver` (original sources retained)           |
| SLSA target            | L2 posture; L3 work in progress                        |

## Build

See `scripts/run-qemu.sh` for the reference local workflow.

Supported machines: `tactiq-qemu-x86`, `tactiq-rock5a`, `tactiq-rock5b`,
`tactiq-rock5t`, `tactiq-generic-arm64`.

## Hardware support and performance reporting

Target platforms: Rock 5A (RK3588S), Rock 5B (RK3588), Rock 5T (RK3588),
generic ARM64 via Yocto machine configs. Additional RK3588-family boards
and a `qemu-x86_64` configuration are supported for build and functional
validation.

Performance metrics are published according to our measurement standard:
multi-sample variance across board units, thermal envelopes under sustained
load, and runtime data from representative workloads. Publication follows
the full qualification cycle.

Board-specific qualification data, once released, will be linked from this
section.

## License

The `meta-tactiq` Yocto layer is licensed under GNU General Public
License version 3 or later (GPL-3.0-or-later). The full text of the
license is in [`LICENSE`](LICENSE).

This applies to the layer code shipped in this repository: machine
configurations, distribution configuration, image recipes, the
TactiQ-specific recipes (`tactiq-agent`, `tactiq-release`,
`tactiq-config`), kernel security fragment, RAUC integration, and
documentation. Components from upstream projects pulled in by the
build retain their own licenses; the resulting image is a
combined work whose distribution follows the requirements of all
constituent licenses.

The license choice reflects the project's positioning. TactiQ OS
is a sovereign edge AI platform foundation: the source must be
available to consumers under terms that guarantee, juridically, the
ability to audit, modify, and redistribute. GPL-3.0-or-later
provides that guarantee. It also aligns with the licenses already
governing the kernel and large parts of the GNU userspace that the
distribution is built on.

Components that may be licensed differently (the TactiQ Edge
ML pipeline, bootloader firmware on TactiQ Module hardware, signed
Doctrine Updates bundles) are separate from this layer and are
licensed according to their own terms; this repository covers the
operating system layer only.
