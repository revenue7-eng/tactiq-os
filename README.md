# meta-tactiq

Yocto layer for TactiQ OS — a security-hardened embedded Linux distribution
for edge AI deployments on Rockchip RK3588 and compatible ARM64 targets.

> **Status: pre-production.** Hardware bring-up phase, no customer
> deployments at this time. Documentation maturity precedes
> implementation maturity at this stage of the project — the
> architectural framework is described in the documents linked from
> the *Architectural principles* section below, while several of the
> implementation steps those documents target are still in progress.

> **Continuous integration:** the CI configuration in `.github/workflows/`
> runs on GitHub Actions and includes lint, shell-check, YAML
> validation, and Yocto recipe lint steps. The full set of checks is
> described in [`SUPPLY_CHAIN.md`](SUPPLY_CHAIN.md).

## Scope

- `conf/distro/tactiq.conf` — systemd + SELinux + TPM2 + seccomp + RAUC; hardened CFLAGS; reproducible-binaries flag on; `sbom-cve-check` enabled; source archiver on.
- `conf/machine/*` — Rock 5A, Rock 5B, Rock 5T, generic ARM64, qemu-x86_64.
- `recipes-core/images/tactiq-image.bb` — production image profile, read-only rootfs, root account locked, no SSH server, `create-spdx` inherited (SPDX 3.0 SBOM per build). This is the canonical recipe for tagged release builds.
- `recipes-core/images/tactiq-image-dev.bb` — development profile retaining `debug-tweaks` and `ssh-server-openssh` for bring-up. Never signed as a release artifact; CI guards enforce that the production recipe stays hardened.
- `recipes-core/rauc/` — RAUC A/B update config. Development keyring shipped in-tree for reproducibility of the development path; production builds override `RAUC_KEYRING_FILE` from CI secrets.
- `recipes-core/tactiq-{agent,config,release}` — attestation agent (Ed25519, runs as the unprivileged `tactiq-agent` user with full systemd sandboxing), runtime config, build info embedded at `/etc/tactiq-release`.
- `recipes-kernel/linux/` — linux-yocto 6.6 LTS pinned, security fragment enabling IMA, SELinux, kernel lockdown groundwork. A sibling bbappend mirrors the fragment for `linux-rockchip` (used by the rock5b machine).

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
| SBOM                   | SPDX 3.0 per build (Yocto `create-spdx`)               |
| CVE scan               | `sbom-cve-check` enabled — CVE report per build          |
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

MIT unless noted per file.
