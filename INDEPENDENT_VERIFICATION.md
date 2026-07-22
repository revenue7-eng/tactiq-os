# Independent verification of a TactiQ OS release

This document describes how a third party — with no access to the
build host, no vendor-supplied caches, and no relationship with the
project — can verify that a published TactiQ OS release corresponds to
the source code in this repository.

The procedure has two layers. The first (§1) verifies the release
without rebuilding anything: signatures, transparency log, artifact
integrity, SBOM structure. It completes in under an hour on a laptop.
The second (§2) rebuilds the release from source on the verifier's own
infrastructure and compares hashes. It requires a build host and takes
several hours.

Either layer can be executed independently. The first is sufficient to
show that the release was produced by the declared workflow from the
declared source state; the second is what independently establishes
that the source state actually reproduces the shipped binaries.

The procedure applies to `v2.1.0-rc6`; later releases follow the same
structure, with the tag substituted throughout.

## 0. Prerequisites

Everything the verifier needs is public:

- this repository at tag `v2.1.0-rc6`
- the release assets published on the GitHub release page
- the upstream Yocto and layer repositories referenced by
  `integration/LAYERS.lock`
- for §2 only: a build host meeting the requirements in §2.1

No credentials, no caches, no configuration files from the build host
are used at any step. If any step below appears to require something
that is not in this list, it is a defect in the release and should be
reported.

## 1. Verification without rebuild

**Purpose.** Confirm that the published release artifacts were signed
by the release workflow of this repository, that their integrity has
not been tampered with, and that the SBOM shipped with them is a
well-formed enumeration of what was built.

**Tools.** `cosign` v2.2 or later, `curl`, `openssl`, `jq`,
`sha256sum`. Installation of `cosign` is covered in `VERIFY.md`.

**Steps.** Follow `VERIFY.md` sections 1–7 verbatim, substituting
`TAG=v2.1.0-rc6`. On successful completion the verifier has established:

- **Signature.** The cosign signature over `SHA256SUMS` verifies
  against the workflow identity
  `https://github.com/revenue7-eng/tactiq-os/.github/workflows/release-sign.yml@refs/tags/v2.1.0-rc6`
  and the OIDC issuer `https://token.actions.githubusercontent.com`.
  The signing certificate is a short-lived Fulcio certificate — no
  long-lived key is trusted.
- **Transparency log.** The corresponding Rekor entry (index
  `2194858421` for rc6, listed in `VERIFY.md §7` for later releases)
  contains a hash of the same `SHA256SUMS` and is fixed in the
  append-only log; any post-hoc substitution would be visible.
- **Artifact integrity.** Every release asset's SHA-256 matches its
  entry in the signed `SHA256SUMS`.
- **SBOM.** `sbom-rock5a.spdx.json` is a valid SPDX 3.0.1 document.
  Each installed package listed in `manifest-rock5a.txt` corresponds
  to a `software_Package` entry; each file has a `software_File`
  entry with a SHA-256 checksum.

This layer of verification does not by itself establish that the
signed binaries were built from the sources in this repository — that
is what §2 does. It does establish that the signed set is internally
consistent and reproducibly identifiable.

## 2. Verification by independent rebuild

**Purpose.** Rebuild the release on an independent build host from
this repository's sources at tag `v2.1.0-rc6`, and confirm that the
resulting artifacts have the same content as the published release.

### 2.1. Build host requirements

- 16 vCPU, 64 GB RAM, 500 GB free disk. Smaller hosts work; a build
  on 8 vCPU / 32 GB takes six to ten hours instead of three to four.
- Ubuntu 24.04 LTS or equivalent, with the Yocto host prerequisites
  installed (see the Yocto Project documentation for the current
  package list).
- Network access to GitHub and the Yocto Project git servers for
  the initial clone; the build itself is offline after `DL_DIR`
  is populated.

No shared caches, mirrors, or artifacts from any other build host are
used. `SSTATE_MIRRORS` is not set. If the verifier chooses to populate
`DL_DIR` from a mirror ahead of time, this does not affect the
verification: source tarballs are content-addressed by upstream
recipes and their SHA-256 is checked on unpack.

### 2.2. Assemble the layer set

```
git clone -b v2.1.0-rc6 https://github.com/revenue7-eng/tactiq-os
cd tactiq-os
./scripts/setup-layers.sh ./layers
```

`setup-layers.sh` reads `integration/LAYERS.lock` and clones every
listed upstream repository at the pinned commit. It fails if any
`HEAD` does not equal its pin. For `meta-rauc` — which has no
upstream `wrynose` branch — it delegates to `setup-meta-rauc.sh`,
which reconstructs the layer by applying a local patch to a pinned
`scarthgap` commit and verifies the result against a hard-coded tree
hash. Origin and provenance of every pin are documented in
`integration/LAYERS.lock`.

### 2.3. Initialize the build directory

```
./scripts/init-build.sh ./layers ./build
```

`init-build.sh` expands `conf/bblayers.conf.in` and `conf/local.conf.in`
into `./build/conf/` with absolute paths pointing at `./layers`. The
templates are minimal: everything security-relevant (SELinux, TPM2,
RAUC, `BUILD_REPRODUCIBLE_BINARIES`, PACKAGE_CLASSES, INHERIT +=
"archiver", sbom-cve-check, security CFLAGS, kernel SPDX inclusion)
is set in `conf/distro/tactiq.conf` and inherited by activating
`DISTRO = "tactiq"`. The verifier can inspect both files in the
build directory before running bitbake.

### 2.4. Build

```
source ./layers/openembedded-core/oe-init-build-env ./build
bitbake tactiq-image
```

Wall-time on a 16 vCPU / 64 GB host is typically three to four hours
for a cold build (empty `DL_DIR` and `SSTATE_DIR`). Subsequent builds
that reuse the same build directory take minutes.

### 2.5. Compare

Three comparison targets, in decreasing order of strength:

1. **Per-file SBOM.** For every `software_File` entry in the newly
   built SBOM (`tmp/deploy/images/tactiq-rock5a/tactiq-image-tactiq-rock5a.rootfs.spdx.json`)
   and the published `sbom-rock5a.spdx.json`, compare the SHA-256
   under the identical file path. Divergence is expected only in the
   four filesystem-level image artifacts (`.ext4`, `.wic`, `.wic.bmap`,
   `.wic.gz`); anything else divergent is a finding.
2. **Kernel and device tree.** SHA-256 of
   `tmp/deploy/images/tactiq-rock5a/Image` and of
   `rk3588s-rock-5a.dtb` in the same directory must match the
   entries for `kernel-rock5a.bin` and `rk3588s-rock-5a.dtb` in the
   signed `SHA256SUMS`.
3. **Rootfs tarball.** The published `sbom-rock5a.spdx.json` records
   the SHA-256 of the rootfs tarball entry. If the verifier's build
   produces a matching tarball hash, the rootfs is bit-identical.

Filesystem-image bit-identity (target 1's exception list) is a known
open item, documented in `SUPPLY_CHAIN.md`. Per-file rootfs
reproducibility (target 1 minus the exception list) and per-artifact
kernel/dtb reproducibility (target 2) are the properties the
architecture guarantees today.

## 3. What a successful verification proves, and what it does not

Successful completion of §1 proves that the release artifacts were
signed by the declared workflow at the declared tag and have not been
altered since. Successful completion of §2 proves that these artifacts
correspond to the sources in this repository at the declared tag.
Together, they establish the property claimed by the accompanying
paper (§5): that an independent party can determine, without vendor
participation, whether the deployed binary matches the published
source.

They do not prove that the source code itself is free of defects,
functional or malicious. Reviewing the source is a separate activity;
what this procedure guarantees is that reviewing the source at
`v2.1.0-rc6` is equivalent to reviewing what the vendor shipped.

## 4. Reporting a discrepancy

If any step of §1 fails, or if §2 produces a divergence outside the
documented exception list, please open an issue in this repository
with the step number, the observed output, and the host environment.
A failed verification is signal, not noise: it is either a defect in
the release or a defect in the procedure, and both are our responsibility
to fix.
