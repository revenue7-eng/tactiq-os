# Security Policy

TactiQ OS is a security-hardened embedded Linux distribution. If you believe
you have found a vulnerability, thank you for taking the time to report it
responsibly.

## Supported versions

Security fixes land on `main` first and are then back-ported to the most
recent release candidate or tagged release. Only the latest tag receives
active security support. Older tags are preserved for historical reference
and are not maintained.

| Version        | Supported          |
|----------------|--------------------|
| v2.1.0-rc4     | :white_check_mark: (canonical) |
| v2.1.0-rc3     | :warning: superseded by rc4 |
| v2.1.0-rc2     | :warning: deprecated — use rc4 (binary payload identical to rc3; see [`docs/release-notes/v2.1.0-rc2-deprecated.md`](docs/release-notes/v2.1.0-rc2-deprecated.md)) |
| v2.1.0-rc1     | :x:                |
| v2.0.1         | :white_check_mark: (critical fixes only) |
| v2.0.0-alpha1  | :x:                |
| < v2.0.0       | :x:                |

## Reporting a vulnerability

Please do **not** open a public issue for security-sensitive reports.

Email security reports to `security@tactiqedge.com`. Reports sent to this
address are triaged by the maintainers.

When reporting, please include:

- Affected component (layer, recipe, machine, kernel config fragment, or
  workflow) and version or commit.
- A description of the issue and the impact you expect.
- A minimal reproduction if possible.
- Any suggested mitigation, if known.

We aim to acknowledge reports within three business days and provide a
status update within seven business days. Coordinated disclosure timelines
are agreed case-by-case with the reporter; the default is 90 days from
initial report to public disclosure, shortened if a fix is already
available.

## CVE handling

This section describes how we handle vulnerabilities at the
distribution level — both CVEs that surface in the upstream
components TactiQ OS depends on, and any CVEs that may be assigned
against TactiQ OS code itself.

**Automated scanning.** Every Yocto build runs CVE analysis against
the NIST NVD feed via the `sbom-cve-check` class; the configuration is
set in `conf/distro/tactiq.conf`
(`IMAGE_CLASSES:append = " sbom-cve-check"`). Tagged releases publish the
resulting CVE manifest as an artifact alongside the SBOM. The
manifest reports both unpatched and patched CVEs — patched ones
are not hidden, so a consumer can verify what fixes are in the
release rather than only what is still open.

**Triage.** Every CVE that appears in the manifest goes through a
triage step before action is taken on it. The triage decides
three things in this order:

1. *Applicability.* Does the CVE apply to the configured TactiQ OS
   build? A CVE in a feature that is not enabled in our distro
   configuration (for example, a Bluetooth vulnerability when
   `bluetooth` is removed from `DISTRO_FEATURES`, or a Wayland
   vulnerability when `wayland` is removed) is recorded as
   not-applicable in the build configuration, with the reason
   noted.
2. *Severity in our context.* The published CVSS score is a
   starting point. The contextual severity for an edge AI
   deployment with a hardened posture may differ — a remote network
   exploitation CVE in a service we do not expose is lower-severity
   in our context, while a local privilege escalation in a path
   under SELinux confinement may be partially mitigated by the
   confinement.
3. *Resolution path.* For an applicable CVE with a meaningful
   severity, the triage decides between back-porting a fix to the
   pinned version, bumping to a patched upstream version, or
   accepting the risk with documented justification when neither
   is feasible. The decision and its justification become part of
   the issue record.

**Upstream tracking.** TactiQ OS depends on a set of upstream
projects, each of which has its own vulnerability response process.
The relevant upstreams and the channels we monitor are:

- **Linux kernel** (linux-yocto 6.6 LTS series) — kernel security
  mailing list and the LTS branch announcements. CVE patches
  applied to the LTS branch flow into TactiQ OS through the
  pinned linux-yocto version when we update the pin, or through
  back-port if a specific fix is needed sooner.
- **Yocto / poky** — upstream Yocto release announcements and
  CVE manifests from the layer's own `sbom-cve-check` runs.
- **meta-rockchip** — layer-specific upstream tracking, including
  vendor firmware blob updates.
- **meta-selinux** — upstream policy and SELinux userspace fixes.
- **Other dependencies** in the SBOM — these are tracked through
  `sbom-cve-check` against the NVD feed; the SBOM ships with each
  release so a consumer can run their own vulnerability
  correlation tooling against it.

**CVE assignment for TactiQ OS code.** If a vulnerability is
identified in code that originates in `meta-tactiq` or
`meta-tactiq-selinux` (rather than in an upstream dependency), and
the maintainers determine it warrants a CVE identifier, the CVE is
requested through MITRE directly via
<https://cveform.mitre.org/>. External reporters who request a CVE
identifier as part of their disclosure are accommodated through
the same channel.

**Public disclosure.** Coordinated public disclosure happens
through a written advisory published in this repository at
`docs/advisories/<CVE-ID>.md` (or, for issues without a CVE
identifier, `docs/advisories/<YYYY-MM-DD>-<short-slug>.md`). Each
advisory carries the affected versions, severity and CVSS score,
patch references with commit hashes, credit to the reporter (with
their consent), and the disclosure timeline. The advisory is
published at the agreed disclosure date or when a fix is generally
available, whichever is later.

## Scope

This policy covers the `meta-tactiq` Yocto layer published in this
repository, the companion `meta-tactiq-selinux` layer, and the CI and
attestation workflows under `.github/workflows/`. It does not cover
upstream dependencies (poky, meta-rockchip, linux-yocto, etc.) — please
report those directly to the relevant upstream project.

The consolidated adversary model that motivates the hardening described
below is in [`THREAT_MODEL.md`](THREAT_MODEL.md).

## Supply-chain posture

TactiQ OS publishes its supply-chain self-assessment in
[`SUPPLY_CHAIN.md`](SUPPLY_CHAIN.md). For `v2.1.0-rc3` a SLSA v1.0
build-provenance attestation was generated at the time of tagging
using
[`actions/attest-build-provenance`](https://github.com/actions/attest-build-provenance)
via Sigstore OIDC; the attestation event is recorded on the public
Sigstore Rekor transparency log at index `1361817475` and remains
inspectable through <https://search.sigstore.dev>.

The integrity binding consumers should rely on for `v2.1.0-rc3` is
the workflow-identity Sigstore signature over `SHA256SUMS`. The
full consumer-side verification procedure is documented in
[`VERIFY.md`](VERIFY.md).

## Security hardening summary

The runtime posture of a TactiQ OS image includes, at minimum:

- SELinux enforcing with a targeted reference policy plus the TactiQ
  custom modules (`tactiq_agent`, `tactiq_vault`, `tactiq_tpm`,
  `tactiq_rauc`, `tactiq_verifier`, `tactiq_ctl`, `tactiq_tamper`,
  `tactiq_fixes`).
- Read-only rootfs with RAUC A/B signed updates.
- `seccomp` syscall filtering; audit subsystem enabled.
- Kernel hardening fragment enabling `CONFIG_IMA`, `CONFIG_IMA_APPRAISE`
  (PCR 10), SELinux, lockdown groundwork.
- Compiler hardening: `-fstack-protector-strong`, `_FORTIFY_SOURCE=2`,
  `relro`, `bind-now`, PIE.
- TPM 2.0 distro feature for measured boot and hardware-rooted key
  material.
- Ed25519 attestation agent at `/opt/tactiq/bin/tactiq-agent`.

Items explicitly not yet wired — and therefore not in scope for a hardened
posture today — are listed in `SUPPLY_CHAIN.md`.

## Credit

Researchers who report valid vulnerabilities in good faith will, with
their consent, be credited in the release notes of the fix. No bug-bounty
program is in place at this time.
