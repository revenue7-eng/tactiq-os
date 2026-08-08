# Verifying TactiQ OS Releases

This document specifies the canonical verification procedure for TactiQ OS
release artifacts. It is intended for security engineers, integrators, and
anyone establishing a chain of trust from a published TactiQ OS release on GitHub.

All commands assume a POSIX shell with `cosign` v2.x, `curl`, `openssl`,
`zstd`, `jq`, and standard GNU coreutils.

A note on identity strings before you start. Several `--certificate-identity`
values below contain `https://github.com/...`. These are the **immutable
historical identities under which the release artifacts were originally
signed**: the workflow ran on GitHub Actions, Sigstore Fulcio recorded
that path in the certificate's Subject Alternative Name, and the
corresponding Rekor entries are append-only. The strings are reproduced
verbatim because `cosign verify-blob` will fail if they are altered.
The Rekor index for releases produced after `v2.1.0-rc3` is documented
in the release notes of each such release.

---

## 0. What you are verifying

A TactiQ OS release carries three independent layers of evidence:

1. **Artifact integrity**: SHA-256 checksums of every release file,
   listed in `SHA256SUMS`.
2. **Signature over `SHA256SUMS`**: produced with Sigstore keyless
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
3. **SLSA build-provenance attestation** over a deterministic source
   archive, produced by GitHub Actions
   (`actions/attest-build-provenance@v2`) when the release is tagged.
   The attested subject is a source archive and never a built artifact,
   so `gh attestation verify` against an image, kernel or bundle asset
   returns 404. That is the designed scope, not a missing attestation.
   The integrity binding consumers rely on for the binaries is the
   workflow-identity signature over `SHA256SUMS` (layer 2 above), whose
   Rekor index is published below. See §5 for what each layer does and
   does not prove.

Each TactiQ OS release carries exactly one cosign signature over its
`SHA256SUMS`. The signing identity differs between release generations:
the personal-identity signature applies to `v2.1.0-rc1` and
`v2.1.0-rc2`, the workflow-identity signature applies to `v2.1.0-rc3`
and later. The workflow identity is the canonical form going forward
because its trust root is a publicly reviewable workflow rather than a
personal account. The personal signature on rc1 and rc2 remains valid
for anyone who needs to verify those earlier tags. Section 7 lists the
Rekor index for each release.

## 1. Prerequisites

```sh
cosign version          # expect >= 2.2
curl --version          # any recent
openssl version         # any recent
zstd --version          # for SBOM tarball decompression
jq --version            # for SBOM JSON inspection
sha256sum --version     # GNU coreutils
```

`cosign` is published on GitHub by the upstream Sigstore project. If
it is missing:

```sh
# Linux x86_64
curl -fsSL -o /usr/local/bin/cosign \
    https://github.com/sigstore/cosign/releases/download/v2.4.1/cosign-linux-amd64
chmod +x /usr/local/bin/cosign
```

## 2. Download

Pick a release tag (`v2.1.0-rc6`, the current release, in the examples below) and pull the
full asset set into a clean working directory.

```sh
TAG=v2.1.0-rc6
BASE=https://github.com/revenue7-eng/tactiq-os/releases/download/${TAG}

mkdir -p "tactiq-os-${TAG}" && cd "tactiq-os-${TAG}"

# Step 1: fetch SHA256SUMS and its signature assets first.
for f in SHA256SUMS \
         SHA256SUMS.workflow.pem SHA256SUMS.workflow.sig \
         SHA256SUMS.pem SHA256SUMS.sig; do
    curl -fsSL --retry 3 -O "${BASE}/${f}" || \
        echo "note: ${f} not present for ${TAG} (rc1/rc2 lack workflow.* ; rc3 and later lack personal *.pem/*.sig)"
done

# Step 2: derive the artifact list from SHA256SUMS itself, then fetch
# every file named in it. This guarantees the download set matches the
# integrity manifest exactly, no drift between docs and the release.
awk '{print $2}' SHA256SUMS | while read -r f; do
    [ -f "${f}" ] && continue
    curl -fsSL --retry 3 -O "${BASE}/${f}"
done
```

The release `SHA256SUMS` itself is signed; once §4 succeeds you have
verified that the list of filenames you used to drive this download
came from the maintainer, not from a man-in-the-middle.

You should now see, at minimum:

- `image-rock5a.wic.gz`, `image-rock5a.wic.bmap` (compressed rootfs image + bmap)
- `kernel-rock5a.bin`, `rk3588s-rock-5a.dtb`
- `manifest-rock5a.txt`, `testdata-rock5a.json`, `buildinfo-rock5a.json`
- `sbom-rock5a.spdx.json` (SPDX 3.0.1 image SBOM)
- `cve-rock5a.sbom-cve-check.yocto.json` (raw),
  `cve-rock5a.enriched.json` (kernel-triaged)
- `SHA256SUMS`
- `SHA256SUMS.workflow.pem`, `SHA256SUMS.workflow.sig` (rc3 and later)
- `SHA256SUMS.pem`, `SHA256SUMS.sig` (rc1, rc2 only)

## 3. Verify artifact integrity

```sh
sha256sum -c SHA256SUMS
```

Every line must print `OK`. A single `FAILED` line invalidates the
release. Stop and report.

## 4. Verify the signature over `SHA256SUMS`

The `--certificate-identity` and `--certificate-oidc-issuer` values
below are reproduced exactly as they were recorded by Sigstore Fulcio
when the releases were signed. They are not editable: changing them
will cause `cosign verify-blob` to reject a valid signature. See the
preamble for the historical context of these identity strings.

### 4.1 Workflow identity (canonical, `v2.1.0-rc3` and later)

```sh
TAG=v2.1.0-rc6
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
if produced by the same workflow. Appendix B explains why this matters.

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

## 5. SLSA build-provenance attestation: scope and status

A SLSA v1.0 build-provenance attestation is generated at tagging time by
[`.github/workflows/attest.yml`](.github/workflows/attest.yml), running
`actions/attest-build-provenance@v2`. It was first issued for
`v2.1.0-rc3`. The attestation event is recorded on the public Sigstore
Rekor transparency log and remains independently inspectable through
<https://search.sigstore.dev>.

**The attested subject is a source archive, not a binary.** The workflow
attests `tactiq-os-<commit>.tar.gz`, built from the tagged commit. No
image, kernel, device tree or RAUC bundle is an attested subject, so:

```sh
gh attestation verify image-rock5a.wic.gz --repo revenue7-eng/tactiq-os
# HTTP 404: no attestations found
```

A 404 here is the expected result and not a defect. Verify the source
archive instead, and rely on the `SHA256SUMS` signature of §4.1 for the
binaries. Reproducing the archive locally and checking it against the
attested digest is the meaningful check:

```sh
git archive --format=tar --prefix="tactiq-os-<commit>/" <commit> \
  | gzip -n > tactiq-os-<commit>.tar.gz
gh attestation verify tactiq-os-<commit>.tar.gz --repo revenue7-eng/tactiq-os
```

**Archive scope by release.** Through `v2.1.0-rc7` the workflow archived
a hand-written list of directories rather than the tree. That list was
measured on 2026-08-07, after the `v2.1.0-rc7` tag was cut, and covers
four of the twenty-seven top-level entries: `conf/`, `recipes-core/`,
`recipes-kernel/`, `scripts/`. It predates `meta-tactiq-bsp-rockchip/`
and `classes-recipe/`, so the BSP layer, the build classes, `pki/`,
`security/` and `postinst-intercepts/` sit outside the attested object
while the workflow describes itself as attesting the sources. A tampered
recipe in the BSP layer is not detectable through provenance at
`v2.1.0-rc7` or any earlier tag. Earlier revisions of this document
described the scope as five directories including a `wic/` tree; no such
directory exists in the repository, and that description was wrong.

The scope is unchanged from `v2.1.0-rc3` through `v2.1.0-rc7`. The fix
removes the list rather than lengthening it: the workflow now runs
`git archive` over `HEAD`, which has no separate idea of what the tree
contains and therefore cannot go stale. It is committed on `main` and
takes effect **from the next tag**; `v2.1.0-rc7` was produced by the
four-directory version and is not covered by it. Determinism of the
replacement was verified locally, two runs byte-identical, 219 entries.

**Standalone verifiable attestation file is not redistributed.** The
attestation event is recorded on Rekor at the time of signing and can be
inspected there; what is not shipped alongside the release is a distinct
attestation asset an external auditor could fetch and verify without a
Rekor lookup. Absence of it does not affect the integrity binding of
§4.1.

**What each layer proves:**

- **Integrity binding, §4.1.** The workflow-identity Sigstore signature
  over `SHA256SUMS`, which transitively covers every release artifact.
  This is the binding consumers should rely on. Per-release Rekor
  indices are listed in §7.
- **Provenance binding**: which workflow, on which commit, produced the
  source archive. Recorded on Rekor at signing time, within the archive
  scope stated above.
- **No SLSA attestation binds the binary artifacts.** The rootfs, kernel
  and device tree are built locally, not in a hosted builder. This is
  the largest open gap toward end-to-end SLSA L3 on the image and is
  tracked in [`SUPPLY_CHAIN.md`](SUPPLY_CHAIN.md). The rootfs is
  reproducible across independent hosts, which is a different and weaker
  property: it shows the build is deterministic under fixed inputs, not
  that the published binaries came from the attested source.

## 6. Verify SBOM integrity

The SBOM is listed in `SHA256SUMS`; step 3 above already covers
it. To inspect content:

```sh
# SPDX 3.0.1 image SBOM: count packages and files
jq '[.["@graph"][] | select(.type=="software_Package")] | length' sbom-rock5a.spdx.json
jq '[.["@graph"][] | select(.type=="software_File")]    | length' sbom-rock5a.spdx.json
```

SBOM scope, what is included and what is not, is documented in
[`SUPPLY_CHAIN.md`](SUPPLY_CHAIN.md#sbom).

## 7. Transparency-log lookup

Every cosign signature above is anchored in the public Rekor log. The
log index for each release is published below; Rekor can also be
queried directly by hash to discover the entry independently:

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

Releases after `v2.1.0-rc3` document their Rekor index in their own
release notes. Current release `v2.1.0-rc6`: index `2194858421`;
`v2.1.0-rc5`: index `1911768787`
(<https://search.sigstore.dev/?logIndex=1911768787>).

---

## Appendix A. Expected identity strings, in full

These strings reproduce verbatim what Sigstore Fulcio recorded in the
respective release certificates. They are not configurable on the
verifier side; passing different values will cause `cosign verify-blob`
to reject a valid signature. The `github.com` URLs reflect the build
infrastructure on which the releases were originally signed and are
preserved as immutable historical artifacts.

```
# Personal identity (rc1, rc2)
--certificate-identity    revenue7@gmail.com
--certificate-oidc-issuer https://github.com/login/oauth

# Workflow identity (rc3 and later), parameterised by tag
--certificate-identity    https://github.com/revenue7-eng/tactiq-os/.github/workflows/release-sign.yml@refs/tags/<TAG>
--certificate-oidc-issuer https://token.actions.githubusercontent.com
```

Identity strings used by releases produced after `v2.1.0-rc3` are
documented in the release notes of each such release.

## Appendix B. Why the tag-SAN check matters

Sigstore bakes the OIDC claims of the signing principal into the X.509
certificate's Subject Alternative Name. For a GitHub Actions workflow,
the SAN encodes the **exact ref that triggered the run**, branch or
tag. A signature produced by the same workflow running on
`refs/heads/main` is cryptographically valid, but its SAN does not
match `refs/tags/<TAG>`, and the corresponding Rekor entry carries the
`main`-identity. A consumer who accepts such a signature is trusting a
mutable branch, not the immutable tag.

The canonical TactiQ OS release-signing workflow is triggered only by
tag pushes (`on: push: tags: ['v*']`). If you encounter a
workflow-identity signature whose SAN does not resolve to the tag you
downloaded, reject it and surface the discrepancy. The Rekor entry is
unremovable but the release signature assets can be (and must be)
replaced with tag-triggered ones.

## Appendix C. Quick one-liner self-check

The short path once all assets are in a clean directory:

```sh
set -e
TAG=v2.1.0-rc6
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
