# Supply-chain posture

This is a self-assessment, not a certification. It describes what the
meta-tactiq layer does today in terms of SLSA v1.0 build track requirements,
what is explicitly tracked as not-yet-done, and where the short-term work is.

Last reviewed: 2026-04-25.

## SBOM

- `INHERIT += "create-spdx"` in `recipes-core/images/tactiq-image.bb`.
- Output: SPDX 2.2, per-recipe and image-level rollup, covering kernel,
  libc, every runtime package with declared license and upstream source.
- `INHERIT += "archiver"` with `ARCHIVER_MODE[src] = "original"` in
  `conf/distro/tactiq.conf` — upstream source tarballs retained.
- **Published in v2.1.0-rc2** as release artifacts:
  - `sbom-image-rock5a.spdx.tar.zst` — primary, 895 SPDX 2.2 documents
    (per-recipe and per-runtime-package).
  - `sbom-image-rock5a-aggregate.spdx.json` — single-file rollup,
    763 packages, 7,178 files with SHA-256 checksums (100% file coverage),
    51,284 relationships.
  - `manifest-rock5a.txt` — plain-text package list (336 packages installed
    in the rock5a rootfs).
- Consumer-side vulnerability correlation tooling is not prescribed.

## CVE scanning

- `INHERIT += "cve-check"` in distro config — every build emits a
  JSON CVE manifest against the NIST NVD feed.
- `CVE_CHECK_REPORT_PATCHED = "1"` so patched CVEs are reported, not hidden.
- The build does not fail on unpatched CVEs in the CI bootstrap phase
  (report-only). Production builds flip this by setting
  `CVE_CHECK_FAIL_ON_UNPATCHED = "1"` in `local.conf`.
- **Published in v2.1.0-rc2** as release artifacts:
  - `cve-full-rock5a.json.gz` and `cve-full-rock5a.txt.gz` — full per-recipe
    CVE summary (NVD2 feed snapshot at build time).
  - `cve-image-rock5a.txt` — per-image CVE rollup.
  - `cve-manifest-rock5a.json` — Yocto-format CVE manifest.

## Reproducible builds

- `BUILD_REPRODUCIBLE_BINARIES = "1"` — Yocto applies `SOURCE_DATE_EPOCH`,
  `REPRODUCIBLE_TIMESTAMP_ROOTFS`, and builds are path-independent.
- Kernel pinned to a specific LTS point-release series in
  `recipes-kernel/linux/linux-yocto_%.bbappend` (no more `6.6%` wildcard).
- Local recipes use `file://` URIs with content shipped in the repo, so
  they are already hash-stable.

### Empirical reproducibility test (v2.1.0-rc2)

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
`/etc/rauc/keyring.pem`.

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
of the update channel is functional in v2.1.0-rc3 — slot lifecycle
and recovery semantics work as described.

**Keyring management — current state.** The build currently uses
the in-tree development certificate `development-1.cert.pem`
(`recipes-core/rauc/files/`) as the RAUC keyring. This is shipped
in the repository for reproducibility of the development path.
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
