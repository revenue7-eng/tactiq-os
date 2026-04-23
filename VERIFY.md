# Verifying TactiQ OS Releases

This document specifies the canonical verification procedure for TactiQ OS
release artifacts. It is intended for security engineers, integrators, and
anyone establishing a chain of trust from a published GitHub release down
to a local root filesystem image.

All commands assume a POSIX shell with `cosign` v2.x, the GitHub CLI `gh`
v2.x (with `gh attestation`), `openssl`, and standard GNU coreutils.

---

## 0. What you are verifying

A TactiQ OS release carries three independent layers of evidence:

1. **Artifact integrity** — SHA-256 checksums of every release file,
   listed in `SHA256SUMS`.
2. **Signature over `SHA256SUMS`** — produced with Sigstore keyless
   signing. Two certificate identities are used depending on the release:
    - **Personal identity** (`revenue7@gmail.com`, OIDC issuer
      `https://github.com/login/oauth`) for `v2.1.0-rc1` and
      `v2.1.0-rc2`. Assets: `SHA256SUMS.pem`, `SHA256SUMS.sig`.
    - **Workflow identity**
      (`https://github.com/revenue7-eng/tactiq-os/.github/workflows/release-sign.yml@refs/tags/<TAG>`,
      OIDC issuer `https://token.actions.githubusercontent.com`) for
      `v2.1.0-rc3` and later, produced by
      [`.github/workflows/release-sign.yml`](.github/workflows/release-sign.yml).
      Assets: `SHA256SUMS.workflow.pem`, `SHA256SUMS.workflow.sig`.
3. **SLSA build-provenance attestation** over the deterministic source
   archive, produced by
   [`.github/workflows/attest.yml`](.github/workflows/attest.yml) via
   `actions/attest-build-provenance@v2`. Retrieved with
   `gh attestation verify`.

Either cosign signature suffices on its own; both point at the same
`SHA256SUMS` file and both are recorded in the public Rekor transparency
log. The workflow-identity signature is the long-term canonical form:
its trust root is a branch-protected workflow on a public repository,
not a personal account.

## 1. Prerequisites

```sh
cosign version          # expect >= 2.2
gh --version            # expect >= 2.40
openssl version         # any recent
sha256sum --version     # GNU coreutils
```

If `cosign` is missing:

```sh
# Linux x86_64
curl -fsSL -o /usr/local/bin/cosign \
    https://github.com/sigstore/cosign/releases/download/v2.4.1/cosign-linux-amd64
chmod +x /usr/local/bin/cosign
```

## 2. Download

Pick a release tag (`v2.1.0-rc3` in the examples below) and pull the
full asset set into a clean working directory.

```sh
TAG=v2.1.0-rc3
mkdir -p "tactiq-os-${TAG}" && cd "tactiq-os-${TAG}"

gh release download "${TAG}" \
    --repo revenue7-eng/tactiq-os
```

You should now see, at minimum:

- `rootfs-rock5a.ext4`, `kernel-rock5a.bin`, `rk3588s-rock-5a.dtb`
- `manifest-rock5a.txt`, `buildinfo-rock5a.json`
- `sbom-image-rock5a.spdx.tar.zst`,
  `sbom-image-rock5a-aggregate.spdx.json`
- `cve-manifest-rock5a.json`, `cve-full-rock5a.json.gz`,
  `cve-full-rock5a.txt.gz`, `cve-image-rock5a.txt`
- `SHA256SUMS`
- `SHA256SUMS.workflow.pem`, `SHA256SUMS.workflow.sig` (rc3 and later)
- `SHA256SUMS.pem`, `SHA256SUMS.sig` (rc1, rc2 only)

## 3. Verify artifact integrity

```sh
sha256sum -c SHA256SUMS
```

Every line must print `OK`. A single `FAILED` line invalidates the
release — stop and report.

## 4. Verify the signature over `SHA256SUMS`

### 4.1 Workflow identity (canonical, `v2.1.0-rc3` and later)

```sh
TAG=v2.1.0-rc3
EXPECTED_IDENTITY="https://github.com/revenue7-eng/tactiq-os/.github/workflows/release-sign.yml@refs/tags/${TAG}"

cosign verify-blob \
    --certificate            SHA256SUMS.workflow.pem \
    --signature              SHA256SUMS.workflow.sig \
    --certificate-identity   "${EXPECTED_IDENTITY}" \
    --certificate-oidc-issuer https://token.actions.githubusercontent.com \
    SHA256SUMS
```

Expected output: `Verified OK`.

The `--certificate-identity` value must match the tag you are verifying.
A certificate whose SAN resolves to `refs/heads/main` or any
non-`refs/tags/<TAG>` ref is **not valid** for a release signature, even
if produced by the same workflow — see Appendix B for why this matters.

### 4.2 Personal identity (`v2.1.0-rc1`, `v2.1.0-rc2`)

```sh
cosign verify-blob \
    --certificate            SHA256SUMS.pem \
    --signature              SHA256SUMS.sig \
    --certificate-identity   revenue7@gmail.com \
    --certificate-oidc-issuer https://github.com/login/oauth \
    SHA256SUMS
```

Expected output: `Verified OK`.

### 4.3 Failure example

A tampered `SHA256SUMS` or a mismatched `--certificate-identity` must
cause verification to fail:

```sh
$ echo 'tampered' >> SHA256SUMS
$ cosign verify-blob \
    --certificate            SHA256SUMS.workflow.pem \
    --signature              SHA256SUMS.workflow.sig \
    --certificate-identity   "${EXPECTED_IDENTITY}" \
    --certificate-oidc-issuer https://token.actions.githubusercontent.com \
    SHA256SUMS
Error: invalid signature when validating ASN.1 encoded signature
```

Do not proceed past this point if cosign reports an error of any kind.

## 5. Verify the SLSA build-provenance attestation

The attestation is produced on the deterministic source archive
(`tactiq-os-<commit>.tar.gz`), not on the binary rootfs. It is therefore
verified against the source archive retrieved from the `attest.yml`
workflow-run artifacts for that tag.

```sh
# Pull the source archive that attest.yml uploaded for this tag
gh run download --repo revenue7-eng/tactiq-os \
    -n tactiq-os-source \
    -D src/

# Verify
gh attestation verify \
    src/tactiq-os-<commit>.tar.gz \
    --repo revenue7-eng/tactiq-os
```

Expected output includes a line confirming the predicate type
`https://slsa.dev/provenance/v1` and a valid OIDC identity matching the
`attest.yml` workflow path.

**What the attestation binds to — and what it does not:**

- **Binds to:** the deterministic source archive
  `tactiq-os-<commit>.tar.gz` produced by `attest.yml`, covering the
  trees `conf/`, `recipes-core/`, `recipes-kernel/`, `scripts/`, `wic/`
  at the tagged commit.
- **Does not bind to:** the rootfs image, kernel binary, or device tree
  blob. These are built outside GitHub Actions today (the full Yocto
  build does not yet run in the hosted builder), so there is no SLSA
  provenance attestation on the binary artifacts. This is the single
  largest gap toward end-to-end SLSA L3 on the image and is tracked as
  a roadmap item in [`SUPPLY_CHAIN.md`](SUPPLY_CHAIN.md).

## 6. Verify SBOM integrity

The SBOM bundle is listed in `SHA256SUMS`; step 3 above already covers
it. To inspect content:

```sh
# Aggregate SPDX JSON — 763 packages, 7,178 files with SHA-256
jq '.packages | length' sbom-image-rock5a-aggregate.spdx.json
jq '.files    | length' sbom-image-rock5a-aggregate.spdx.json

# Per-recipe SPDX documents (one per Yocto recipe)
mkdir -p sbom && cd sbom
zstd -d ../sbom-image-rock5a.spdx.tar.zst -c | tar -xf -
ls | wc -l
```

SBOM scope — what is included, what is not — is documented in
[`SUPPLY_CHAIN.md`](SUPPLY_CHAIN.md#sbom).

## 7. Transparency-log lookup

Every cosign signature above is anchored in the public Rekor log. The
log index is recorded in the release notes for each tag; Rekor can also
be queried directly:

```sh
# By hash of SHA256SUMS
rekor-cli search --sha "$(sha256sum SHA256SUMS | awk '{print $1}')"
```

Web UI: <https://search.sigstore.dev>.

Known Rekor indices:

| Release     | Index                | Identity  |
|-------------|----------------------|-----------|
| v2.1.0-rc2  | `1361157130`         | personal  |
| v2.1.0-rc3  | `1361817475`         | workflow  |

---

## Appendix A — expected identity strings, in full

```
# Personal identity (rc1, rc2)
--certificate-identity    revenue7@gmail.com
--certificate-oidc-issuer https://github.com/login/oauth

# Workflow identity (rc3+), parameterised by tag
--certificate-identity    https://github.com/revenue7-eng/tactiq-os/.github/workflows/release-sign.yml@refs/tags/<TAG>
--certificate-oidc-issuer https://token.actions.githubusercontent.com
```

## Appendix B — why the tag-SAN check matters

Sigstore bakes the OIDC claims of the signing principal into the X.509
certificate's Subject Alternative Name. For a GitHub Actions workflow,
the SAN encodes the **exact ref that triggered the run** — branch or
tag. A signature produced by the same workflow running on
`refs/heads/main` is cryptographically valid, but its SAN does not
match `refs/tags/<TAG>`, and the corresponding Rekor entry carries the
`main`-identity. A consumer who accepts such a signature is trusting a
mutable branch, not the immutable tag.

The canonical TactiQ OS release-signing workflow is triggered only by
tag pushes (`on: push: tags: ['v*']`). If you encounter a
workflow-identity signature whose SAN does not resolve to the tag you
downloaded, reject it and surface the discrepancy — the Rekor entry is
unremovable but the release signature assets can be (and must be)
replaced with tag-triggered ones.

## Appendix C — quick one-liner self-check

The short path once all assets are in a clean directory:

```sh
set -e
TAG=v2.1.0-rc3
ID="https://github.com/revenue7-eng/tactiq-os/.github/workflows/release-sign.yml@refs/tags/${TAG}"

sha256sum -c SHA256SUMS
cosign verify-blob \
    --certificate            SHA256SUMS.workflow.pem \
    --signature              SHA256SUMS.workflow.sig \
    --certificate-identity   "${ID}" \
    --certificate-oidc-issuer https://token.actions.githubusercontent.com \
    SHA256SUMS
echo "release ${TAG}: integrity + signature OK"
```

If any step fails, the release should be treated as untrusted until the
failure is explained on the record.
