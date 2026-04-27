# Verifying TactiQ OS Releases

This document specifies the canonical verification procedure for TactiQ OS
release artifacts. It is intended for security engineers, integrators, and
anyone establishing a chain of trust from a published TactiQ OS release on
Codeberg down to a local root filesystem image.

All commands assume a POSIX shell with `cosign` v2.x, `curl`, `openssl`,
`zstd`, `jq`, and standard GNU coreutils.

A note on identity strings before you start. Several `--certificate-identity`
values below contain `https://github.com/...`. These are the **immutable
historical identities under which the release artifacts were originally
signed**: the workflow ran on GitHub Actions, Sigstore Fulcio recorded
that path in the certificate's Subject Alternative Name, and the
corresponding Rekor entries are append-only. The strings are reproduced
verbatim because `cosign verify-blob` will fail if they are altered. They
do **not** imply that the project is currently hosted on GitHub — the
canonical home is this Codeberg repository. The signing path used for
releases produced after `v2.1.0-rc3` is documented in the release notes
of each such release.

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
   archive, originally produced by GitHub Actions
   (`actions/attest-build-provenance@v2`) at the time the release was
   tagged. For `v2.1.0-rc3` the attestation is a historical record on
   the Sigstore Rekor transparency log; the integrity binding consumers
   rely on for this release is the workflow-identity signature over
   `SHA256SUMS` (layer 2 above), whose Rekor index is published below.
   See §5 for the full status and the limits of what each layer proves.

Either cosign signature suffices on its own; both point at the same
`SHA256SUMS` file and both are recorded in the public Rekor transparency
log. For `v2.1.0-rc3` the workflow-identity signature is the canonical
form — its trust root is a publicly reviewable workflow rather than a
personal account, and it is the path with no caveats. The personal
signature on rc1 and rc2 remains valid for anyone who needs to verify
those earlier tags.

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

Pick a release tag (`v2.1.0-rc3` in the examples below) and pull the
full asset set into a clean working directory.

```sh
TAG=v2.1.0-rc3
BASE=https://codeberg.org/revenue7-eng/tactiq-os/releases/download/${TAG}

mkdir -p "tactiq-os-${TAG}" && cd "tactiq-os-${TAG}"

# Step 1: fetch SHA256SUMS and its signature assets first.
for f in SHA256SUMS \
         SHA256SUMS.workflow.pem SHA256SUMS.workflow.sig \
         SHA256SUMS.pem SHA256SUMS.sig; do
    curl -fsSL --retry 3 -O "${BASE}/${f}" || \
        echo "note: ${f} not present for ${TAG} (rc1/rc2 lack workflow.* ; rc3 lacks personal *.pem/*.sig only if absent on the release page)"
done

# Step 2: derive the artifact list from SHA256SUMS itself, then fetch
# every file named in it. This guarantees the download set matches the
# integrity manifest exactly — no drift between docs and the release.
awk '{print $2}' SHA256SUMS | while read -r f; do
    [ -f "${f}" ] && continue
    curl -fsSL --retry 3 -O "${BASE}/${f}"
done
```

The release `SHA256SUMS` itself is signed; once §4 succeeds you have
verified that the list of filenames you used to drive this download
came from the maintainer, not from a man-in-the-middle.

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

The `--certificate-identity` and `--certificate-oidc-issuer` values
below are reproduced exactly as they were recorded by Sigstore Fulcio
when the releases were signed. They are not editable: changing them
will cause `cosign verify-blob` to reject a valid signature. See the
preamble for why these strings reference `github.com` even though the
project lives on Codeberg.

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

## 5. SLSA build-provenance attestation — status for `v2.1.0-rc3`

A SLSA v1.0 build-provenance attestation was generated for `v2.1.0-rc3`
at the time of tagging. The attestation was produced by GitHub Actions
running `actions/attest-build-provenance@v2`, bound to the deterministic
source archive `tactiq-os-<commit>.tar.gz` covering the trees `conf/`,
`recipes-core/`, `recipes-kernel/`, `scripts/`, `wic/` at the tagged
commit. The attestation event is recorded on the public Sigstore Rekor
transparency log and remains independently inspectable through
<https://search.sigstore.dev>.

**Reproducible verification of the attestation file itself by an
external auditor is not provided for `v2.1.0-rc3` on Codeberg.** The
canonical retrieval path for an `attest-build-provenance` attestation
is the GitHub-specific `gh attestation verify` command, which is not
applicable to a release hosted outside GitHub. The attestation was
produced before the project's release-publishing path moved to
Codeberg; re-issuing an equivalent attestation on the Codeberg-hosted
release is a separate engineering task tracked alongside the CI
migration.

**What this means for trust in `v2.1.0-rc3`:**

- **Integrity binding is provided by §4.1** — the workflow-identity
  Sigstore signature over `SHA256SUMS`, which transitively covers
  every release artifact. Rekor index for this signature: `1361817475`.
  This is the binding consumers should rely on.
- **Provenance binding** (which workflow, on which commit, produced the
  source archive) is recorded on Rekor at the time of signing and can
  be observed there, but is not redistributed as a standalone
  verifiable file alongside the Codeberg release for `v2.1.0-rc3`.
- **No SLSA attestation binds the binary artifacts** themselves —
  rootfs, kernel, device tree. These are built locally (WSL2 + Docker),
  not in a hosted builder. This is the largest open gap toward
  end-to-end SLSA L3 on the image and is tracked in
  [`SUPPLY_CHAIN.md`](SUPPLY_CHAIN.md).

**Going forward.** The signing and attestation path for releases
produced after `v2.1.0-rc3` is documented in the release notes of
each such release. Releases that ship a standalone, externally
verifiable attestation file as a release asset will document the
exact verification command in their own release notes; absence of
such a file means the release inherits the same status as `rc3`
above.

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

---

## Appendix A — expected identity strings, in full

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

# Workflow identity (rc3), parameterised by tag
--certificate-identity    https://github.com/revenue7-eng/tactiq-os/.github/workflows/release-sign.yml@refs/tags/<TAG>
--certificate-oidc-issuer https://token.actions.githubusercontent.com
```

Identity strings used by releases produced after `v2.1.0-rc3` are
documented in the release notes of each such release.

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
