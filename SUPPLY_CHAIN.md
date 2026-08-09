# Supply-chain posture

This is a self-assessment, not a certification. It describes what the
meta-tactiq layer does today in terms of SLSA v1.0 build track requirements,
what is explicitly tracked as not-yet-done, and where the short-term work is.

Last reviewed: 2026-06-22.

## SBOM

- `INHERIT += "create-spdx"` in `recipes-core/images/tactiq-image.bb`.
- Output: a single self-contained SPDX 3.0.1 image SBOM covering the kernel,
  libc, and every runtime package with declared license and upstream source.
  Under wrynose the image SBOM already *is* the aggregate; there is no
  per-recipe `.spdx.tar.zst` to unpack.
- `INHERIT += "archiver"` with `ARCHIVER_MODE[src] = "original"` in
  `conf/distro/tactiq.conf` — upstream source tarballs retained.
- `SPDX_INCLUDE_COMPILED_SOURCES:pn-linux-yocto = "1"` in
  `conf/distro/tactiq.conf` — the kernel SPDX carries its compiled-sources
  file list, consumed by the CVE enrichment below.
- **Published** as release artifacts:
  - `sbom-rock5a.spdx.json` — the SPDX 3.0.1 image SBOM (self-contained
    aggregate: packages, files with SHA-256, relationships).
  - `manifest-rock5a.txt` — plain-text package list (273 packages installed
    in the rock5a rootfs).
- Consumer-side vulnerability correlation tooling is not prescribed.

## CVE scanning

- `IMAGE_CLASSES:append = " sbom-cve-check"` in distro config — every
  build runs CVE analysis against the NIST NVD feed (Yocto wrynose
  replaced the removed `cve-check` class with `sbom-cve-check`).
- Patched CVEs are reported rather than hidden.
- The build is report-only by default (does not fail on unpatched CVEs).
  Failing on unpatched CVEs is a `local.conf` policy toggle.
- **Published** as release artifacts:
  - `cve-rock5a.sbom-cve-check.yocto.json` — the raw per-build CVE report
    from `sbom-cve-check` (NVD feed snapshot at build time).
  - `cve-rock5a.enriched.json` — kernel-triaged report. A post-assembly step
    (`scripts/enrich-cve.sh`, run inside `mk-release.sh`) feeds the raw report,
    the kernel compiled-sources SPDX, and a linux-vulns snapshot through
    OE-core's `improve_kernel_cve_report.py`: CVEs in kernel code not compiled
    into our config are ignored, and version-not-in-range entries resolved.

### CVE posture (v2.1.0-rc6)
Image-scoped, high-severity (CVSS v3 base ≥ 7.0), status `Unpatched`: **134**
(108 kernel, 26 userspace). Honest disclosure, not a patched count — rc6 is a
candidate; drive-to-zero is a GA gate.

This is up from **35** (21 kernel, 14 userspace) in rc5, and the rise is real
rather than a change of scope: the kernel pin did not move between the two
releases (`6.18.24+git` in both), and 85 of the 108 kernel entries are
`CVE-2026-*` published in the month between them. Moving the pin is tracked
in issue #55 and was excluded from rc6 so that the enforcing-boot and OTA
verification in that release are measured against an unchanged base.

The counting rule is reproducible and is documented step by step in
`docs/release-notes/v2.1.0-rc6.md`: installed packages from the manifest are
mapped to recipes with `oe-pkgdata-util lookup-recipe`, and the enriched
report is filtered to that set. Package and recipe names differ
(`libc6` → `glibc`), so a naive string comparison drops most of the image.
Without the scope filter the same report yields 141.

Triage notes:
- Breakdown by detail: 110 `version-in-range`, 24 `no-version-ranges`.
- Userspace is led by openssl ×9 and glibc ×5.
- 3 SELinux-family entries continue to match the rc5 not-applicable finding:
  the vulnerable `seunshare` sandbox tool is not packaged (only
  `policycoreutils-setfiles` is installed). VEX pending.

## Reproducible builds

- `BUILD_REPRODUCIBLE_BINARIES = "1"` — Yocto applies `SOURCE_DATE_EPOCH`,
  `REPRODUCIBLE_TIMESTAMP_ROOTFS`, and builds are path-independent.
- Kernel pinned to a specific LTS point-release series in
  `recipes-kernel/linux/linux-yocto_%.bbappend` (no more `6.6%` wildcard).
- Local recipes use `file://` URIs with content shipped in the repo, so
  they are already hash-stable.

### Empirical reproducibility test (v2.1.0-rc2, scarthgap)

Two consecutive builds against the same tagged source state, with `sstate`
cache reused on the second build. Full methodology, raw `cmp(1)` output,
and per-region analysis are in
[`docs/reproducibility/v2.1.0-rc2.md`](docs/reproducibility/v2.1.0-rc2.md).

| Metric                     | Value                                |
|----------------------------|--------------------------------------|
| `rootfs.ext4` size         | 369,253,376 bytes (identical)        |
| Bytes identical            | 369,043,867 (99.943%)                |
| Bytes differing            | 209,509 (0.057%)                     |
| Distinct diff ranges       | 54,024                               |
| Mean range size            | ~3.9 bytes                           |

Differences localized to ext4 inode metadata (per-file mtime / ctime / atime,
including 4-byte nanosecond fields), filesystem header (UUID, hash seed,
mkfs timestamp), backup superblock copies, and metadata files generated at
rootfs assembly time (machine-id, random-seed).

**Per-file content reproducibility verified** via the published SBOM —
the SPDX aggregate records SHA-256 for 7,178 files, and these hashes are
identical between the two builds.

### Empirical reproducibility test (wrynose, 2026-07-21)

Re-measured after migration from scarthgap to wrynose (Yocto 6.0).
Two consecutive builds of `tactiq-image` (builds 20260721003000 and
20260721023917, second with warm sstate). Full methodology and raw data
are in [`docs/reproducibility/wrynose-20260721.md`](docs/reproducibility/wrynose-20260721.md).

| Metric                     | Value                                |
|----------------------------|--------------------------------------|
| SBOM format                | SPDX 3.0.1 (single image SBOM)      |
| Files with SHA-256 in SBOM | 38,951                               |
| Files identical            | 38,947 (99.99%)                      |
| Files differing            | 4 (image artifacts only)             |
| `.wic` image size          | 9,785,328,640 bytes (identical)      |
| Bytes identical            | 9,785,255,562 (99.9993%)             |
| Bytes differing            | 73,078                               |
| Distinct diff ranges       | 15,805                               |
| Mean range size            | ~4.6 bytes                           |
| Manifest packages          | 273 (identical)                      |
| rootfs tarball              | bit-identical (SHA-256 match)        |

The 4 differing files are image-level artifacts (`.ext4`, `.wic`,
`.wic.bmap`, `.wic.gz`) whose differences are filesystem metadata
(ext4 UUID, inode timestamps, partition table). The rootfs tarball
(`.tar.gz`) is bit-identical, confirming that every file in the
root filesystem — kernel, libc, every runtime package — produces
byte-identical output from the same source on wrynose.

**Per-file content reproducibility verified on wrynose.**

**Filesystem-image bit-identity not yet achieved.** Pending elimination
of remaining non-deterministic sources: `mkfs.ext4 --uuid` pinning,
inode-timestamp normalization to `SOURCE_DATE_EPOCH`, deterministic
`machine-id` and `random-seed` generation. Yocto upstream has open work
in this area; we plan to track and adopt it.

**Not yet done:** CI job running two independent builds on clean workers
and diffing image artifacts as a gate. The Yocto machinery is in place;
the verification step is not running on every merge.

## Build provenance

- `image-buildinfo` class inherited; `tactiq-release` package writes
  `/etc/tactiq-release` into every image — version, codename, UTC build
  date, machine target, meta-layer git short hash, image basename.
- For `v2.1.0-rc3`, a SLSA build-provenance attestation was generated
  on GitHub Actions at the time of tagging, using
  `actions/attest-build-provenance@v2` with GitHub's OIDC identity and
  Sigstore as a non-falsifiable generator. The attestation was bound
  to the SHA-256 of a deterministic source archive and recorded on the
  public Sigstore Rekor transparency log. The current status of the
  attestation file with respect to consumer-side verification is in
  [`VERIFY.md`](VERIFY.md) §5.
- **Not yet done:** even when re-issued, the attestation binds to the
  source archive, not to the final rootfs image. Extending this to
  attest image binaries requires moving a full Yocto build into a
  hosted builder, which is the main gating item for SLSA L3.

## Release-artifact signing (Sigstore keyless)

- v2.1.0-rc2 release artifacts are protected by a Sigstore signature over
  `SHA256SUMS`, which transitively covers every release artifact — the
  rootfs image, kernel binary, device tree, SBOM bundle, aggregate SPDX,
  CVE reports, manifest, and buildinfo.
- Signing identity: `revenue7@gmail.com` via GitHub OIDC issuer
  (`https://github.com/login/oauth`).
- Tooling: `cosign sign-blob` with a Fulcio-issued ephemeral X.509 cert.
  No long-lived keys.
- Public Rekor transparency log entry: `1361157130`
  (https://search.sigstore.dev/?logIndex=1361157130).

Verification:

```
cosign verify-blob \
  --certificate SHA256SUMS.pem \
  --signature SHA256SUMS.sig \
  --certificate-identity revenue7@gmail.com \
  --certificate-oidc-issuer https://github.com/login/oauth \
  SHA256SUMS

# then transitively:
sha256sum -c SHA256SUMS
```

## Image signing (boot path)

- FIT image signing in the U-Boot path: not yet implemented. The
  composite kernel-plus-DTB-plus-initramfs payload is delivered to
  the bootloader unsigned in the current build pipeline.
- RK3588 OTP-fused secure boot root: not yet activated. The OTP
  fuses on the reference development hardware are not burned, which
  means the SoC boot ROM does not enforce a public-key root for the
  first loaded stage. OTP burn is the last step in the boot chain
  hardening sequence because it is irreversible.
- IMA userspace appraisal policy: not yet deployed. The kernel is
  built with `CONFIG_IMA=y`, `CONFIG_IMA_APPRAISE=y`, PCR 10 — the
  kernel-level machinery is present, the on-disk policy that tells
  the kernel which files require valid signatures and what to do
  on verification failure is not yet deployed.

The complete chain of trust from the silicon root to the running
attestation agent, including per-stage status, is documented in
[`BOOT_CHAIN.md`](BOOT_CHAIN.md).

## Update channel

Software updates are delivered through RAUC. The system
configuration in `recipes-core/rauc/files/system.conf` defines an
A/B partition layout: two ext4 root slots (`rootfs_a` and
`rootfs_b`), bootloader-driven slot switching through U-Boot
environment, compatible string `tactiq-edge` for bundle
compatibility checks, and the on-device verification keyring at
`/etc/rauc/root-ca.pem`.

**Bundle integrity.** Each RAUC bundle is signed by the keyring
configured at build time. The device verifies the signature against
the on-device keyring before installing the bundle. A bundle
modified in transit, or a bundle signed by an unrecognized key,
fails verification and is not installed. This verification is
local — it does not depend on the delivery channel having any
particular property.

**Atomic A/B switch and recovery.** Bundle installation writes the
new image into the inactive slot; the bootloader marks that slot
as pending. On reboot, the bootloader counts boot attempts; if the
boot completes successfully within the configured limit, the slot
is marked good and becomes active. If boot fails repeatedly, the
bootloader rolls back to the previously known-good slot. This part
of the update channel is functional and has been exercised on hardware:
rollback from a corrupted slot is recorded in
`measurements/rauc-rollback-test-20260716.md`, and bundle installation under
SELinux enforcing in `measurements/selinux-enforcing-boot-prod-20260717.log`.
Through rc5 the bundle recipe packaged the *development* rootfs; from rc6 it
carries the production image.

**Keyring management: current state.** The build currently uses the
in-tree development root `pki/dev/root-ca.pem` as the RAUC keyring, the
same hierarchy used for kernel module signing. Its private keys are in
the repository on purpose, so that the verification can be reproduced
from outside without access to anything held privately.
Production builds require a separate keyring loaded from CI
secrets at build time, so that the production verification key is
not present in the public source tree. The transition from the
in-tree development keyring to a CI-secret-provisioned production
keyring is tracked as a near-term roadmap item; it is the same
keyring transition that gates the FIT signing path described
above.

**Anti-rollback.** RAUC bundle metadata supports a generation
counter, and the bootloader can be configured to refuse to boot a
candidate slot whose generation is lower than the platform has
already accepted. The machinery exists; the bootloader-enforced
check is not yet wired in v2.1.0-rc3. Without this enforcement, a
correctly-signed older bundle can be downgraded onto a device.
This is tracked alongside the FIT signing work.

**Delivery model.** RAUC's verification is signature-anchored and
channel-independent: the bundle file can be delivered through any
mechanism that delivers a file. In TactiQ OS deployments the
assumed default is offline delivery (USB media, secondary SD card,
local network without internet egress). HTTPS-based delivery is
supported but not required by the architecture. This matches the
broader offline-first posture documented in
[`THREAT_MODEL.md`](THREAT_MODEL.md) and
[`ATTESTATION.md`](ATTESTATION.md).

**Out of scope at this layer.** The identity of the update
endpoint (proving that a delivered bundle came from the expected
source rather than from a middleman with a valid signature) is a
per-deployment configuration concern, not a distro-level property.
Bandwidth optimization, delta updates, and update-progress
reporting are operational features outside the current scope.

## Measurement evidence: integrity and image scope

The threat-coverage manifest for a tag cites files under `measurements/`
as evidence, referencing them by path.

**Integrity.** The manifest is hashed into `SHA256SUMS` and covered by
the release signature. The files it cites are not. `measurements/` is
outside the release artifact set, so the integrity of the cited
evidence rests on git history alone. `measurements/SHA256SUMS` is an
index for local comparison. It is unsigned, it sits in the same tree as
the files it hashes, and its entries cover a different set of files
than the manifest cites.

**Image scope.** The eleven citations in the rc7 manifest resolve to
four files. `selinux-enforcing-boot-prod-20260717.log` was taken on the
production profile, on v2.0.0-rc6, in July 2026.
`rauc-rollback-test-20260716.md` and `rauc-pki-unify-20260806.md` were
taken on the development profile `tactiq-image-dev.bb`.
`cve-posture-rc7-20260807.md` analyses a build report and names no
image. The development profile keeps passwordless
root, an SSH server and the SELinux policy tooling, and is never signed
as a release artifact. The production profile `tactiq-image.bb` removes
those items and inherits the rest by `require`. A result from the
development image therefore covers the shared base only.

These limits bear on each other. Placing the cited files under the
release signature would extend that signature over measurements taken
on an image that is never released. The integrity gap stays open until
the evidence is retaken on the production profile. No date is set for
that here.

## SLSA self-assessment

SLSA v1.0 build track, per the current posture:

| Requirement                                 | State    |
|---------------------------------------------|----------|
| Scripted build                              | Met      |
| Build process documented                    | Met      |
| Provenance exists                           | Met for `v2.1.0-rc3` (recorded on Rekor at tagging time) |
| Provenance authentic (signed, non-falsifiable generator) | Met for tagged source archives via Sigstore OIDC |
| Provenance service-generated                | Met for `v2.1.0-rc3` (GitHub Actions) |
| Hosted build platform                       | Partial — lint and attestation pipeline runs on GitHub Actions; full image build is local (WSL2 + Docker) |
| Hermetic build                              | Not met  |
| Two-person review gate on builder config    | Not met  |
| Parameterless / reproducible                | Partial — machinery on; per-file content reproducibility empirically verified (see above); filesystem-image bit-identity not yet achieved |

**Claimed level: L2 posture for `v2.1.0-rc3` source-archive provenance
(verifiable via Rekor index `1361817475`). L1 for the full rootfs
image, pending migration of the image build into a hosted builder.**

## Short-term roadmap

1. Move a minimal rootfs build (qemu-x86_64) into GitHub Actions and
   extend the SLSA attestation to the image artifact. This is the
   single biggest lift toward end-to-end L2 on the image itself.
2. Wire the two-independent-builds bit-for-bit diff as a required check
   (machinery already exists; needs CI job).
3. Eliminate remaining non-deterministic sources in `do_image_ext4` and
   `do_rootfs` (mkfs UUID pinning, inode timestamp normalization,
   deterministic machine-id and random-seed) to push filesystem-image
   reproducibility from per-file content to bit-identity.
4. Replace the development RAUC keyring in the production build path with
   a keyring loaded from CI secrets at build time.
5. Stand up IMA appraisal with a minimal policy covering `/opt/tactiq/`
   and `/usr/lib/systemd/system/tactiq-*`.
