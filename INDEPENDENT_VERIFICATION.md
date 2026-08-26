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
- `cargo` on the host, for the agentgateway vendoring step in §2.3a.
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
./scripts/setup-layers.sh ../layers
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
./scripts/init-build.sh ../layers ./build
```

`init-build.sh` expands `conf/bblayers.conf.in` and `conf/local.conf.in`
into `./build/conf/` with absolute paths pointing at `../layers`. The
templates are minimal: everything security-relevant (SELinux, TPM2,
RAUC, `BUILD_REPRODUCIBLE_BINARIES`, PACKAGE_CLASSES, INHERIT +=
"archiver", sbom-cve-check, security CFLAGS, kernel SPDX inclusion)
is set in `conf/distro/tactiq.conf` and inherited by activating
`DISTRO = "tactiq"`. The verifier can inspect both files in the
build directory before running bitbake.

### 2.3a. Vendor the agentgateway crate tree

```
./scripts/vendor-agentgateway.sh ./build/downloads
```

`agentgateway` builds from a vendored crate tree because three of its
dependencies come from git forks that the crate fetcher cannot express.
The script clones the pinned revision, runs `cargo vendor --locked`, and
refuses to proceed unless the resulting tree hashes to the value recorded
in the script. Without this step `bitbake tactiq-image` fails in
`agentgateway:do_configure` with "vendored crate tree missing". The step
was introduced in #115 and first documented here after the `v2.1.0-rc9`
cold builds failed on it.

### 2.4. Build

```
source ../layers/openembedded-core/oe-init-build-env ./build
bitbake tactiq-image
```

Measured cold-build wall-time on a 32 vCPU / 64 GB host with empty
`DL_DIR` and `SSTATE_DIR`, 5,254 tasks: 33 m 23 s (2026-07-30), and
41 m 41 s and 43 m 59 s for the two independent builds of 2026-08-02.
The three-to-four-hour figure previously given here was an estimate
for a 16 vCPU host, not a measurement. Subsequent builds that reuse
the same build directory take minutes.

### 2.5. Compare

Three comparison targets, in decreasing order of strength:

1. **Per-file SBOM.** For every `software_File` entry in the newly
   built SBOM (`tmp/deploy/images/tactiq-rock5a/tactiq-image-tactiq-rock5a.rootfs.spdx.json`)
   and the published `sbom-rock5a.spdx.json`, compare the SHA-256
   under the identical file path.
2. **Device tree.** SHA-256 of `rk3588s-rock-5a.dtb` in
   `tmp/deploy/images/tactiq-rock5a/` must match the corresponding
   entry in the signed `SHA256SUMS`.
3. **Rootfs tarball.** The published `sbom-rock5a.spdx.json` records
   the SHA-256 of the rootfs tarball entry. If the verifier's build
   produces a matching tarball hash, the rootfs is bit-identical.

What counts as an expected divergence is a property of the specific
release, not of the procedure, and is stated here per release.
Anything divergent that is not listed for the release under
verification is a finding, and §4 applies.

#### v2.1.0-rc6

| Class | Expected | Reason |
|---|---|---|
| Image containers (`.ext4`, `.wic`, `.wic.bmap`, `.wic.gz`) | yes | ext4 metadata: filesystem UUID, inode timestamps, mkfs timestamp |
| `/etc/tactiq-release` | yes | records build identity, volatile by design |
| Kernel image, 18 kernel modules, 4 kernel-meta logs | yes, for this release only | unpinned module-signing key, see below |
| Anything else | no | finding |

Excluding the classes above, userspace reproduces per-file: 38,694 of
38,695 files identical on an independent cold rebuild, on unrelated
infrastructure, twelve days after the reference build.

The kernel-side exception is not a tolerance. In `v2.1.0-rc6`,
`CONFIG_MODULE_SIG` was enabled with `CONFIG_MODULE_SIG_KEY` left at
its default, so the kernel build generated a fresh RSA key pair on
every build starting from a clean tree: the certificate was compiled
into the built-in keyring and the private half signed every module
under `CONFIG_MODULE_SIG_ALL`. The signing key was an unpinned build
input. The key that signed the published `rc6` artifacts was
ephemeral and no longer exists, so no party can byte-reproduce the
`rc6` kernel image or its modules. For `rc6`, kernel integrity rests
on signed-artifact provenance (§1) and the measured boot chain, not
on independent rebuild. The device tree lies outside the signing path
and does reproduce, which is why it is target 2 above.

This defect was found by executing this procedure against our own
release. It is fixed forward: the signing key is now a pinned,
published development artifact, and two independent cold builds of
the fixed tree, sharing no build state, produced a bit-identical
`rootfs.tar.gz` (SHA-256
`41b668379ae8561206896ec9ad62b71ba9a04d9c48c112ade32c4d696d1b7140`),
with divergence confined to the image containers. The measurement is
in `docs/reproducibility/`.

Filesystem-image bit-identity remains a known open item, documented
in `SUPPLY_CHAIN.md`.

## 3. What a successful verification proves, and what it does not

Successful completion of §1 proves that the release artifacts were
signed by the declared workflow at the declared tag and have not been
altered since. Successful completion of §2 proves that these artifacts
correspond to the sources in this repository at the declared tag, for
the file set that the release under verification reproduces (§2.5).
Where a release carries a documented kernel-side exception, that part
of the image is covered by §1 alone.
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
