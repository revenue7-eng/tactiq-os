# Supply-chain posture

This is a self-assessment, not a certification. It describes what the
meta-tactiq layer does today in terms of SLSA v1.0 build track requirements,
what is explicitly tracked as not-yet-done, and where the short-term work is.

Last reviewed: 2026-04-22.

## SBOM

- `INHERIT += "create-spdx"` in `recipes-core/images/tactiq-image.bb`.
- Output: SPDX 2.2, per-recipe and image-level rollup, covering kernel,
  libc, every runtime package with declared license and upstream source.
- `INHERIT += "archiver"` with `ARCHIVER_MODE[src] = "original"` in
  `conf/distro/tactiq.conf` — upstream source tarballs retained.
- **Not yet done:** publishing SBOMs as signed release artifacts alongside
  images. Consumer-side vulnerability correlation tooling is not prescribed.

## CVE scanning

- `INHERIT += "cve-check"` in distro config — every build emits a
  JSON CVE manifest against the NIST NVD feed.
- `CVE_CHECK_REPORT_PATCHED = "1"` so patched CVEs are reported, not hidden.
- The build does not fail on unpatched CVEs in the CI bootstrap phase
  (report-only). Production builds flip this by setting
  `CVE_CHECK_FAIL_ON_UNPATCHED = "1"` in `local.conf`.

## Reproducible builds

- `BUILD_REPRODUCIBLE_BINARIES = "1"` — Yocto applies `SOURCE_DATE_EPOCH`,
  `REPRODUCIBLE_TIMESTAMP_ROOTFS`, and builds are path-independent.
- Kernel pinned to a specific LTS point-release series in
  `recipes-kernel/linux/linux-yocto_%.bbappend` (no more `6.6%` wildcard).
- Local recipes use `file://` URIs with content shipped in the repo, so
  they are already hash-stable.
- **Not yet done:** CI job running two independent builds on clean workers
  and diffing image artifacts bit-for-bit as a gate. The Yocto machinery
  is in place; the verification step is not running on every merge.

## Build provenance

- `image-buildinfo` class inherited; `tactiq-release` package writes
  `/etc/tactiq-release` into every image — version, codename, UTC build
  date, machine target, meta-layer git short hash, image basename.
- `.github/workflows/attest.yml` runs on tag pushes and calls
  `actions/attest-build-provenance@v2`, which generates a signed SLSA
  build-provenance statement using GitHub's OIDC identity and Sigstore
  as a non-falsifiable generator. Attestations are bound to the SHA-256
  of a deterministic source archive.
- **Not yet done:** the attestation currently binds to the source archive,
  not to the final rootfs image. Extending this to attest image binaries
  requires moving a full Yocto build into a hosted builder, which is the
  main gating item for SLSA L3.

## Signing

- RAUC A/B updates are signed — currently with the development
  `development-1.cert.pem` keyring shipped in-tree for reproducibility of
  the dev path. Production images consume a separate keyring provisioned
  out-of-band.
- **Not yet done:** FIT image signing; RK3588 OTP-fused secure boot root;
  IMA userspace appraisal policy (the kernel is built with
  `CONFIG_IMA=y`, `CONFIG_IMA_APPRAISE=y`, PCR 10 — kernel-level machinery
  is present, the signing policy on disk is not deployed).

## SLSA self-assessment

SLSA v1.0 build track, per the current posture:

| Requirement                                 | State    |
|---------------------------------------------|----------|
| Scripted build                              | Met      |
| Build process documented                    | Met      |
| Provenance exists                           | Met      |
| Provenance authentic (signed, non-falsifiable generator) | Met for tagged source archives via Sigstore OIDC |
| Provenance service-generated                | Met for tagged archives (GitHub Actions) |
| Hosted build platform                       | Partial — CI runs lint and attestation; full image build is still local (WSL2 + Docker) |
| Hermetic build                              | Not met  |
| Two-person review gate on builder config    | Not met  |
| Parameterless / reproducible                | In progress (machinery on, gate not running) |

**Claimed level: L2 posture for the components built in CI
(layer source archive). L1 for the full rootfs image, pending migration
of the image build into a hosted builder.**

## Short-term roadmap

1. Move a minimal rootfs build (qemu-x86_64) into GitHub Actions and extend
   the attestation to the image artifact. This is the single biggest lift
   toward end-to-end L2 on the image itself.
2. Wire the two-independent-builds bit-for-bit diff as a required check.
3. Replace the development RAUC keyring in the production build path with
   a keyring loaded from CI secrets at build time.
4. Publish SBOM and CVE manifest as release artifacts next to signed images.
5. Stand up IMA appraisal with a minimal policy covering `/opt/tactiq/`
   and `/usr/lib/systemd/system/tactiq-*`.
