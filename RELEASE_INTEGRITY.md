# Release integrity: keyring, FIT signing, initramfs, RIM

This document specifies the mechanisms through which TactiQ OS produces
release artifacts whose integrity is independently verifiable end-to-end
— from the production signing keyring through to the Reference Integrity
Manifest consumed by attestation verifiers. It sits alongside
`BOOT_CHAIN.md` (chain of trust from silicon root to running agent),
`SUPPLY_CHAIN.md` (supply-chain self-assessment), `KERNEL_HARDENING.md`
(kernel hardening posture), and `ATTESTATION.md` (attestation framework
specification).

This is a v0.2 design document. v0.1 received external security review;
v0.2 responds to that review. Changes from v0.1 are summarized in
Appendix A. Where the current implementation differs from the
mechanisms described here, the difference is named explicitly.

Last reviewed: TODO.

## Status

Seven areas are specified here. The first five close gaps named in
other documents; the last two state explicitly the boundaries of what
this document is and is not.

| Area                         | Gap closed                                              | Blocker for                          |
|------------------------------|---------------------------------------------------------|--------------------------------------|
| Production keyring lifecycle | `SUPPLY_CHAIN.md` § "Update channel" keyring rotation   | All other roadmap steps              |
| FIT image signing            | `BOOT_CHAIN.md` § Roadmap steps 2 + 3                   | Verified boot from bootloader onward |
| Initramfs composition        | `KERNEL_HARDENING.md` § "Initramfs" acknowledged gap    | FIT image signing                    |
| RIM (Reference Integrity Manifest) | `ATTESTATION.md` § "Implementation roadmap" step 4 | End-to-end attestation verifiability |
| TPM class disclosure         | Reconciles `THREAT_MODEL.md` § 6 with product-facing docs | Honest external positioning        |
| Adversarial CI threat model  | Names CI compromise scenarios and their mitigations     | Honest external positioning        |
| Catastrophic compromise recovery | Names what happens when the signing path itself is compromised | OTP burn safety                |

Each area is independently designed. They share design principles
documented in §1.

## 1. Design principles

These principles apply to all areas. They derive from
`DESIGN_PRINCIPLES.md` and are restated here so that decisions in
later sections can be checked against them.

**Sovereignty of operator keys.** No part of the release integrity chain
requires trust in TactiQ Engineering as a long-lived signing authority.
Operators rebuilding from source under their own keyring must produce
a functionally identical chain. The default TactiQ keyring is the
production reference, not the only permissible root.

**Workflow identity over personal identity.** Where Sigstore keyless
signing applies (release artifacts, SBOM, RIM), the signing principal
is a tag-triggered GitHub Actions workflow identity, not a personal
account. The tag-SAN binding described in `VERIFY.md` Appendix B
applies to every signature this document specifies.

**Per-product keyring scope.** The release integrity chain serves
TactiQ OS as a foundation layer. Products built on top of it (TactiQ
Edge, TactiQ Box) sign their own artifacts with their
own keys. The keyring hierarchy in §2 reflects this.

**Air-gap compatibility is a property of the verifier setup, not of
the verification step.** Every verification step is performable
without network access, **provided the verifier has previously fetched
the Sigstore trust bundle** (Fulcio root certificate, Rekor public
key, current CT log artifacts) into local storage. The bundle is
itself a distributable file; once fetched, no further network access
is required. Online transparency-log lookup is supplementary, never
required. This is a clarification over v0.1, which implied air-gap
verification works without preconditions — it does not.

**Reproducibility and signing are layered, neither substitutes for the
other.** A signed artifact whose source build is not reproducible
allows the consumer to verify "this is what TactiQ signed" but not
"this is what the source code produces". Reproducibility allows the
consumer to verify the second without trusting the signer. TactiQ OS
pursues both, with the current state documented in `SUPPLY_CHAIN.md`
(per-file content reproducibility at 99.943% byte identity; filesystem
image bit identity not yet achieved; hermetic builder not yet in
place). Until full bit-identity is achieved on a hermetic builder, the
chain is **signing-anchored with reproducibility as supporting
evidence**, not the inverse. This is a clarification over v0.1, which
overstated the reproducibility position.

## 2. Production keyring lifecycle

### 2.1 Hierarchy

TactiQ release integrity uses a keyring hierarchy with three scopes.
Each scope is named, has a defined holder, defined lifetime, defined
materialization rules, and defined revocation procedure.

| Scope             | Holder                          | Lifetime     | Materialization                                    | Used to sign                                |
|-------------------|---------------------------------|--------------|----------------------------------------------------|---------------------------------------------|
| Release root      | Air-gapped material under TactiQ Engineering control. **Never enters any CI runner under any condition.** | Years (rotated on incident or scheduled audit) | Air-gapped signing host; signature artifacts committed to repository | Per-product key certificates; revocation list entries |
| Per-product key   | GitHub Actions encrypted secret per repository                | Annual rotation, on-incident replacement | Materialized into CI runner memory at start of tag-triggered workflow; removed at end | Release artifacts of that product (FIT images) |
| Per-build identity| Ephemeral Sigstore Fulcio cert (keyless OIDC)               | Per-tag (~minutes)                       | Issued by Fulcio at signing time; private key never persists | `SHA256SUMS`, SBOM, RIM of one specific release |

**Critical clarification over v0.1:** the release root is **air-gapped
without exception**. It is not "usually offline" or "stored as a
secret elsewhere". It is on a machine that has never had network
connectivity since the key material was generated. Signing operations
performed by the release root produce artifacts (signed per-product
key certificates, signed revocation list entries) that are then
transferred to the repository through controlled means (USB media,
review, commit). No code path in CI has the capability to invoke the
release root. This is the property that allows recovery from CI
compromise to remain possible (§8).

### 2.2 Why two day-to-day keys and not one

The bootloader and userspace verifiers have different trust models.

**U-Boot** must verify the FIT image before any userspace runs. It can
only validate RSA signatures embedded in its own DTB; it has no
network, no Fulcio, no Rekor. Therefore U-Boot trusts an
RSA public key compiled into its DTB at build time — the per-product
key in its public half.

**`cosign verify-blob`**, run by a release consumer or by the
attestation verifier, validates Sigstore keyless signatures against
Fulcio. The trust root is the GitHub Actions workflow identity, not a
long-lived key.

These two verification paths are independent. A consumer downloading
a release tag from GitHub validates the per-build Fulcio signature
over `SHA256SUMS`. A device booting validates the per-product RSA
signature embedded in the FIT image. Both signatures cover the same
artifacts, by different mechanisms, for different audiences.

### 2.3 Materialization in CI

The per-product RSA private key is stored as a GitHub Actions
encrypted secret with restricted access scope:

- Repository: `revenue7-eng/tactiq-os`
- Secret name: `TACTIQ_OS_FIT_SIGNING_KEY` (placeholder; final name TBD)
- Access: workflow runs triggered by tag pushes matching `v*` only;
  the release-sign workflow is the only workflow with permission to
  read this secret
- Environment protection: production environment with required
  reviewers (Andrey Lazarev, Denis Brilkov) configured in the GitHub
  environment settings
- Key format: PEM-encoded RSA-3072
- Public half: committed to the repository at
  `recipes-bsp/u-boot/files/tactiq-fit-signing.pub.pem` along with a
  release-root signature over its certificate body, so that any
  rebuild reproduces the same DTB and the per-product key's
  authenticity is auditable through the release root, not through
  TactiQ's word

The private key is never written to disk in the runner; it is loaded
into the `mkimage` invocation through environment variable and lives
only in process memory. The runner is the ephemeral GitHub-hosted
ubuntu-latest image; no self-hosted runners are used for release
signing.

The threat model for this materialization path — what fails if it is
compromised, and what is mitigated vs not mitigated — is in §7.

### 2.4 Key rotation

**Scheduled rotation: annual.** Every 12 months a new per-product key
is generated. The release root signs the new key's certificate body
on the air-gapped signing host. The signed certificate body is
committed to the repository in a new release branch. Subsequent
releases use the new key. The old key's public half and its
release-root signature remain in the repository history so that older
releases remain verifiable.

**Incident rotation: immediate.** If the per-product key is suspected
compromised: the air-gapped signing host produces a revocation list
entry naming the compromised key fingerprint, signed by the release
root. The revocation list is published as a signed artifact in the
repository. A new per-product key is generated; its certificate body
signed by the release root; the next release ships with the new key.

**The revocation list is not a CRL in the X.509 sense.** It is an
append-only list of revoked TactiQ per-product keys, signed by the
release root, distributed as a file. Consumers fetch and verify the
list as they would any other release artifact. A device in the field
checks its installed keyring against the revocation list during update
verification and refuses updates signed by revoked keys.

**The revocation list trust path is independent of the per-product
key.** A consumer verifying the revocation list checks the release
root signature, not any CI-materialized signature. This is what
prevents a CI-compromise scenario from producing a fake revocation
list that revokes legitimate keys and authorizes attacker keys: the
revocation list signing is air-gapped, the CI never has the capability
to produce a valid revocation list entry. (Addresses review pt. 12.)

### 2.5 Compatibility with OTP burn

OTP fuses on the SoC encode the hash of **the release root's public
key**, not of any per-product key. U-Boot at boot time loads its own
DTB, finds the per-product key with its release-root signature,
verifies the signature using the release root public key hash from
the OTP, and only then trusts the per-product key for FIT signature
verification.

This is a change from v0.1, which described OTP encoding the
per-product key hash directly. v0.1 was wrong: that approach would
lock the platform to a single per-product key for life, making
incident rotation impossible on OTP-burned devices.

**Per-product key rotation post-OTP-burn:** annual scheduled rotation
works. The new per-product key's certificate is signed by the release
root; U-Boot validates this chain at boot; the platform accepts the
new key. The OTP root never changes.

**Release root rotation post-OTP-burn:** not supported by signing
chain alone. If the release root is compromised on OTP-burned
platforms, recovery requires a physical recovery path. This is the
catastrophic scenario in §8.

### 2.6 Initial transition to a production keyring

The current in-tree development RAUC keyring is `pki/dev/root-ca.pem`,
the same root used for kernel module signing. Its private keys are public
by design (see `pki/README.md`), so development-signed bundles can be built
and checked by anyone from the tag alone. That property is what makes the
keyring a development one: it authenticates nothing. The transition path to
a keyring that does:

1. **Generate the release root** on an air-gapped signing host.
   Hardware: a workstation or laptop dedicated to this purpose, with
   no network interfaces enabled, kept in a controlled location.
   Operating system: a verified-boot Linux with full disk encryption,
   not running TactiQ OS itself (separation of concerns — the release
   root signs TactiQ OS releases, so it must not be part of the
   release-signing chain).
2. **Document the release root.** Fingerprint, safe-storage location,
   access protocol, recovery procedure are recorded in a separate
   document (`KEY_CUSTODY.md`, not public). The custody document is
   reviewed by both founders.
3. **Generate the first per-product key.** On the air-gapped host,
   produce its certificate body and sign it with the release root.
   The signed certificate body becomes a file in the repository.
4. **Add the GitHub Actions secret** containing the per-product
   private half.
5. **Update `recipes-core/rauc/`** to consume `RAUC_KEYRING_FILE`
   from CI secrets when building production images, retaining
   `pki/dev/root-ca.pem` as the default for development builds. Note that
   the signer's `check-purpose` in `system.conf` must match the extended
   key usage of whichever signer the production hierarchy issues.
6. **Tag the first release** built with the production keyring;
   publish release notes documenting the keyring transition.

Until step 6 is complete, no release should claim production-keyring
status. Releases v2.1.0-rc1 through rc6 inclusive use the development
keyring; this is documented in their release notes. Up to and including
rc7 the image shipped a keyring whose private half existed nowhere, so no
bundle could be installed at all; that defect is described in
`measurements/rauc-pki-unify-20260806.md`.

### 2.7 What this section does not cover

- **Key custody procedures for the release root.** Offline storage
  medium (hardware security module, paper backup, threshold sharing),
  physical location, access protocol, and recovery procedure are an
  operational concern documented in `KEY_CUSTODY.md` (not public).
- **Per-product keys for products other than TactiQ OS.** TactiQ Edge
  and TactiQ Box each maintain their own per-product
  keys under the same release root, in their own repositories. The
  hierarchy is shared; the per-product key material is not.
- **Threshold signing for the release root.** A future hardening step
  in which the release root requires multiple holders to co-sign is
  named in §8 as a long-term direction, not specified here.

## 3. FIT image signing

### 3.1 What is signed

A FIT (Flat Image Tree) image is a U-Boot container format combining
multiple binary payloads in a single signed structure. The TactiQ OS
FIT image contains:

- Kernel image (`Image`)
- Device tree blob (`*.dtb`, machine-specific)
- Kernel command line (as part of the configuration node)

The FIT image is signed with the per-product key (§2.3). U-Boot
verifies the signature before extracting any payload. A FIT image
whose signature does not validate against the public key embedded in
U-Boot's own DTB is refused.

Note the absence of initramfs from the FIT payload list. See §4 for
the rationale.

### 3.2 Where signing happens

Signing happens in the Yocto build, not in a separate post-build
step. The mechanism is the upstream `kernel-fitimage` class with
`UBOOT_SIGN_ENABLE = "1"`, `UBOOT_SIGN_KEYDIR` pointing at the
CI-provided key directory, and `UBOOT_SIGN_KEYNAME` set to the
per-product key name.

The build receives the per-product private key through the GitHub
Actions secret (§2.3); it is materialized into the build sandbox at
the start of the release workflow and removed at the end. Local
developer builds do not have access to the production key and produce
either unsigned FIT images (for QEMU testing) or images signed with
the development keyring (for hardware bring-up).

The CI guard described in `SUPPLY_CHAIN.md` (production image must not
contain `debug-tweaks`) is extended: a production image must contain
a FIT image signed by the production per-product key, and must not be
buildable in a local developer environment.

### 3.3 What U-Boot must do

U-Boot configuration for this machine must set:

- `CONFIG_FIT_SIGNATURE=y`
- `CONFIG_FIT_SIGNATURE_MAX_SIZE` sized for the expected FIT
- `CONFIG_RSA=y`
- `CONFIG_SHA256=y`
- The release root's public key hash matched against the OTP-fused
  hash where OTP is burned (§2.5)
- The per-product key with its release-root signature compiled into
  the U-Boot DTB at build time, via the `mkimage -K` flow

The U-Boot recipe in `meta-tactiq-bsp-rockchip/recipes-bsp/u-boot/`
must be updated to:

- Pull the public key and its release-root signature from
  `recipes-bsp/u-boot/files/`
- Embed them into the control DTB during the U-Boot build
- Set the verify-required flag so that an unsigned FIT image is
  refused

A U-Boot built without the public key embedded will accept any FIT
image; this is the current state. After the integration in this
section, an attempt to boot an unsigned or mis-signed image fails at
the bootloader.

### 3.4 Kernel command line

`KERNEL_HARDENING.md` and `BOOT_CHAIN.md` both observe that the kernel
command line is part of the chain of trust and is currently unsigned.
The FIT image format includes the kernel command line as part of the
configuration node that is covered by the signature. After §3
integration, the kernel command line is signed along with the kernel
image and DTB.

This closes the kernel-command-line gap named in both
`KERNEL_HARDENING.md` § "Kernel command line" and `BOOT_CHAIN.md`
§ "Kernel command line".

### 3.5 Anti-rollback

`BOOT_CHAIN.md` § Roadmap step 4 names anti-rollback enforcement as a
separate item. FIT signing does not provide anti-rollback by itself —
a correctly signed older image is, by signature alone, still valid.

Anti-rollback is implemented through the RAUC bundle generation
counter (RAUC machinery is in place; bootloader enforcement is not).
After §3 integration, the bootloader checks the RAUC slot's recorded
generation counter against the platform's accepted minimum, recorded
in U-Boot environment. The minimum increases when an update succeeds;
slots whose recorded generation is below the minimum are refused at
boot.

The U-Boot environment storing the minimum-generation counter must
itself be protected; the simplest mechanism is to store it in a TPM
NV index analogous to the attestation freshness counter in
`ATTESTATION.md` § "Freshness mechanism". This binds rollback
resistance to the TPM-backed monotonic counter — a hardware property
rather than a software-stored value.

### 3.6 What this section does not cover

- **Bootloader stages before U-Boot.** Idbloader (rkbin proprietary
  blob) and any vendor TPL/SPL stages are vendor-bound. Verification
  of these stages depends on OTP burn (§2.5).
- **Network booting.** TactiQ OS images do not boot from network; PXE
  and tftpboot paths are not in scope.
- **Recovery boot signing.** Recovery slot images are signed with the
  same per-product key as production slots. There is no separate
  recovery keyring.

## 4. Initramfs composition

`KERNEL_HARDENING.md` § "Initramfs" names initramfs composition as an
acknowledged gap. This section closes it.

### 4.1 Position

**No initramfs.** TactiQ OS boots directly from the kernel into the
root filesystem on the rootfs partition selected by the bootloader.
This is consistent with read-only rootfs (no early-userspace mount
manipulation needed), with A/B slot layout (slot selection happens in
U-Boot via extlinux config, not in userspace), and with attack
surface reduction (initramfs is acknowledged in the kernel hardening
documentation as a known weak shoulder).

### 4.2 What this means in practice

Yocto's default kernel-image recipe builds an initramfs only when
`INITRAMFS_IMAGE` is set. TactiQ OS does not set it. The image recipe
in `recipes-core/images/tactiq-image.bb` does not include an
initramfs target.

The root filesystem partition is selected through the kernel command
line (`root=PARTLABEL=rootfs_a` or `root=PARTLABEL=rootfs_b`,
selected by extlinux through the U-Boot environment). The kernel
mounts the root filesystem directly; there is no early-userspace
phase between kernel start and `/sbin/init` execution.

### 4.3 Trade-offs accepted

**No emergency recovery shell on boot failure.** A traditional
initramfs provides a fallback shell when the root filesystem fails to
mount (corrupt filesystem, wrong device, missing module). Without
initramfs, a kernel that cannot mount root panics and the bootloader
falls through to the alternate slot via the RAUC A/B recovery
mechanism. This is acceptable: TactiQ OS is not a desktop or
general-purpose distribution, and "drop the operator into a shell" is
not an appropriate failure mode for a hardened edge device.

**Disk-related kernel modules must be built-in, not loadable.**
Without initramfs there is no opportunity to load modules before root
mount. The kernel config must build storage controllers, filesystem
drivers (ext4), and crypto primitives (for any future dm-verity
integration) as `=y`, not `=m`. This is a constraint on the kernel
config fragment but not a hardship — the set of supported storage
controllers is bounded by the supported MACHINEs.

**No early-boot key unsealing.** Some Linux distributions perform TPM
key unsealing in initramfs to mount an encrypted root. TactiQ OS uses
read-only rootfs which is not encrypted; the encryption boundary is
the application data partition (`/data`), not the root. Data
partition key unsealing happens in userspace after init, in the
tactiq-agent context.

### 4.4 What this section does not cover

- **dm-verity on rootfs.** Named as Phase 3 work in
  `KERNEL_HARDENING.md`. dm-verity does not require initramfs when
  the verity superblock is on the same partition and the verity
  module is built-in. The integration is straightforward when the
  rest of Phase 3 lands.
- **Recovery partition.** A dedicated recovery slot beyond the A/B
  layout is not currently planned. The A/B slot pair plus the data
  partition is the complete partition set.

## 5. Reference Integrity Manifest (RIM)

`ATTESTATION.md` § "Implementation roadmap" step 4 names RIM
generation as a deliverable. This section specifies the format,
publication, lifecycle, and — critically over v0.1 — the matching
semantics for PCR values, which are not "exact byte equality" for all
PCRs.

### 5.1 PCR matching policy

PCR values are not all reproducible to byte identity even on
correctly-built identical systems. Firmware drift, vendor blob
versions, measurement ordering inside TF-A and OP-TEE, and per-boot
timing variations all produce small differences in PCR 0–7 between
otherwise-equivalent boots. Exact-equality PCR matching, as implied
by v0.1, would produce false positives in operation and make the
attestation system unusable.

The RIM specifies per-PCR matching semantics:

| PCR range | What it measures                                    | RIM matching semantics                                    |
|-----------|-----------------------------------------------------|-----------------------------------------------------------|
| 0–3       | SoC ROM, vendor early-boot firmware (TF-A, OP-TEE)  | Set of allowed values per platform configuration (allow-list). Values vary with vendor firmware version; allow-list is updated when an audited new vendor firmware is qualified. |
| 4–5       | U-Boot binary, U-Boot environment                   | Exact match. U-Boot binary is reproducible from the source tree under our control. |
| 6–7       | U-Boot configuration, SecureBoot policy             | Exact match where the inputs are reproducible; allow-list with documented values where they reflect platform variability not under our control. |
| 8         | Kernel image                                        | Exact match. Kernel binary is built reproducibly under our control. |
| 9         | DTB and any kernel-command-line measurement          | Exact match. Both are signed into the FIT image (§3.4) and reproducible. |
| 10        | IMA runtime measurements                            | Event-log replay against a reference IMA template, not PCR equality. The verifier replays the device's reported IMA event log; the resulting PCR 10 value must match the reported value (proves log integrity); the events themselves must subset the reference template (proves no unexpected measured files). |

**Why this works.** The RIM does not need to predict every byte the
TPM will report. It needs to allow the verifier to decide, given the
attestation, whether the platform is in an expected state. For PCRs
we control end-to-end (kernel, DTB, command line), exact match is the
strongest possible check. For PCRs we don't control (vendor firmware,
some bootloader stages), the allow-list approach matches a known set
of qualified configurations and rejects everything else — including
attacker-modified firmware that produces a PCR value the allow-list
has never seen. For PCR 10, the event log replay approach is the
industry-standard mechanism for runtime measurement verification; it
is what Keylime does and what TCG specifications recommend.

**Updating the allow-list.** When a new vendor firmware version is to
be qualified (e.g. an updated TF-A release from Rockchip), the
process is: build TactiQ OS against the new firmware in a controlled
environment, boot a reference device, record the PCR 0–3 values, add
them to the allow-list in the RIM schema for that platform, sign the
new RIM as part of the release that adopts the new firmware. The
qualification step is the trust anchor; the allow-list is the
machine-readable expression of that trust. (Addresses review pt. 6.)

### 5.2 What a RIM contains

A RIM is a per-build, per-machine manifest of the expected platform
state. It contains:

- **Build identity.** Same fields as `/etc/tactiq-release`: version,
  codename, UTC build date, machine target, **full meta-layer git
  commit SHA** (not short), image basename. Full SHA addresses the
  collision-risk concern with short hashes.
- **Per-PCR matching specification.** For each TPM PCR in the range
  0–10: matching semantics (exact / allow-list / event-log-replay)
  and the values that constitute the match, per §5.1.
- **IMA reference template.** The set of IMA measurement entries
  the kernel will produce for the protected paths
  (`/opt/tactiq/`, `tactiq-*` systemd units) during a clean boot,
  expressed as a partial-order specification (the runtime log is
  not byte-identical run-to-run because of file access ordering,
  but the set of measured files and their hashes is).
- **Kernel command line.** The exact command-line string signed
  into the FIT image (§3.4).
- **U-Boot version and configuration fingerprint.**
- **Per-product key fingerprint.** Which per-product key signed
  the FIT image this RIM describes.
- **Release root fingerprint.** Which release root certified the
  per-product key. Allows the verifier to validate the full chain.

### 5.3 Format

JSON-Lines, signed per-entry, with a final block-level signature over
the canonical hash of all entries. Schema reference:
`schemas/rim-v1.json` in this repository (to be added with the first
RIM-producing release).

### 5.4 Publication

A RIM is a release artifact, published alongside `SHA256SUMS`, the
SBOM bundle, and the CVE reports for the same release. It is:

- Listed in `SHA256SUMS` with its SHA-256
- Signed by the per-build Fulcio identity (the same signature that
  covers `SHA256SUMS` transitively covers the RIM)
- Distributable as a single file for offline use, provided the
  verifier has the Sigstore trust bundle (per §1 air-gap
  clarification)

A verifier validating an attestation against a RIM performs:

1. Fetch the RIM for the build identity claimed by the attestation
2. Verify the RIM's Sigstore signature against the expected workflow
   identity for that release tag (per `VERIFY.md` § 4.1)
3. Verify the RIM's `SHA256SUMS` line matches the file's actual hash
4. For each PCR, apply the matching semantics from §5.1 against the
   attestation-reported value
5. Replay the attestation's IMA event log; verify it produces the
   reported PCR 10; verify the log entries subset the reference
   template
6. Accept or reject based on the combined result

### 5.5 What a RIM does not encode

- **Workload-specific state.** The RIM describes the platform; what
  runs on the platform (AI models, application data, configuration
  beyond `/etc/tactiq-release`) is outside its scope. Workload
  attestation is an application-layer concern, restated from
  `THREAT_MODEL.md` § TCB.
- **Acceptable variation across deployments.** A RIM describes one
  build. A device fleet running the same build matches the same
  RIM; cross-build attestation verification requires the verifier to
  hold the RIMs for all builds in the fleet.
- **Policy decisions.** The RIM tells the verifier what to expect.
  Whether a mismatch triggers QUARANTINE, alert, or grace period is
  a verifier-side policy, not a RIM-side specification.

## 6. TPM class disclosure

This section reconciles `THREAT_MODEL.md` § 6 with product-facing
documents. The OS-side architectural posture is unchanged; the
disclosure language is made consistent.

### 6.1 What the OS supports

TactiQ OS supports two TPM classes:

- **Discrete TPM 2.0** — separate chip, hardware-isolated key
  material, attestation primitives backed by chip-level isolation
- **Firmware TPM (fTPM)** — implementation inside the SoC's
  secure-world TEE (OP-TEE on ARM TrustZone), software-isolated key
  material, attestation primitives backed by TEE isolation
  guarantees

The kernel TPM driver configuration in `tactiq-security.cfg` accepts
both classes; the attestation framework in `ATTESTATION.md` operates
the same protocol over both.

### 6.2 What product positioning may claim

- **TactiQ OS as a distribution:** "TPM 2.0 based attestation" without
  further qualification. The OS itself is class-neutral.
- **TactiQ OS on a specific MACHINE configuration:** the available
  TPM class for that platform, named explicitly, with the threat
  model parameters from `THREAT_MODEL.md` § 6.
- **TactiQ Box or any specific product:** the TPM
  class delivered with the product. If the product ships with a
  discrete TPM chip (e.g. Infineon SLB9670), that is stated. If it
  uses the SoC's fTPM, that is stated. Product positioning that
  does not name the class is incomplete and should be revised before
  external use.

### 6.3 What this means for current product-facing material

- `Product_Overview` describes "TPM 2.0 (hardware security module)"
  without qualifying class. On RK3588 reference hardware this is
  fTPM, not a discrete chip. The product overview should distinguish
  between (a) the OS supporting both classes and (b) the specific
  product configuration delivering one of them. This is a marketing
  edit, not an architectural change.
- `Platform_Strategy` and `Landscape` documents do not require
  changes for this — they describe positioning at the platform level,
  not at the per-product level.

### 6.4 What this section does not cover

- **Hardware redesign decisions.** Whether TactiQ Box (or any other
  TactiQ product) should be redesigned to include a discrete TPM
  chip is a product-level decision driven by target market threat
  model expectations, not an OS-level decision.
- **Vendor fTPM implementation review.** The strength of fTPM on
  RK3588 depends on the OP-TEE implementation and on RK3588 TEE
  security advisories. Tracking this is a hardware-validation
  concern documented per platform in `docs/machines/`, not in this
  document.

## 7. Adversarial CI threat model

The mechanisms in §2–§6 specify what the release pipeline does on the
happy path. This section names what happens off the happy path:
specifically, when CI itself is the adversary. The section is
deliberately separated so that mitigations are not confused with
guarantees. (Addresses review pt. 7.)

### 7.1 Capabilities considered

The following adversary capabilities are considered in scope:

**A1. Malicious maintainer.** An individual with commit access acts
in bad faith. Capability includes pushing arbitrary commits, creating
release tags, approving environment gates if listed as a reviewer.

**A2. Compromised maintainer credentials.** GitHub credentials of a
legitimate maintainer are stolen. Capability is the same as A1 from
the perspective of the platform, lower from the perspective of
intent.

**A3. Compromised GitHub organization.** Administrative control of
the GitHub organization passes to an adversary, through credential
theft of an org owner, GitHub support compromise, or social
engineering. Capability includes adding workflows, modifying
environment protections, adding secrets, changing branch protection
rules.

**A4. Poisoned reusable workflow.** A workflow file in the
repository or in a referenced external repository is modified to
exfiltrate secrets or to insert malicious content into signed
artifacts.

**A5. Compromised dependency in the build pipeline.** An upstream
package consumed by the Yocto build (poky, meta-openembedded, a
specific recipe's source URL) ships malicious content. The build
incorporates it; the resulting image is signed correctly by the
production keyring because nothing in the pipeline detects the
compromise.

**A6. Compromised GitHub Actions runner.** The ephemeral
ubuntu-latest runner image ships with a backdoor; or, the GitHub
Actions service itself is compromised between job dispatch and
signing.

### 7.2 What is mitigated

**Against A1 and A2** — tag-only trigger plus required reviewers
plus environment protection means that a single compromised account
cannot produce a release without independent approval. Reviewer
approval is a manual step performed by a human looking at a diff;
this provides some defense, with the obvious caveat that reviewer
diligence is itself a trust assumption.

**Against A3, A4 in part** — branch protection rules require
reviewed pull requests; the release-sign workflow is itself a
committed file under that branch protection; modifying it requires a
reviewed commit. A workflow change to exfiltrate secrets is visible
in the diff that the reviewer is approving.

**Against A5** — SBOM generation, CVE scanning, and reproducible
builds together provide some defense: a compromised dependency
introduces content that is visible in the SBOM, may match a known
CVE, and breaks per-file reproducibility if not bit-identical with
prior builds. The current state of reproducibility (per-file content
identity, not bit identity at image level) limits the strength of
this defense.

**The revocation list trust path is preserved against all of A1–A6**
— because the revocation list is signed by the air-gapped release
root (§2.4), no capability listed in this section produces a valid
revocation list entry. After detection of any compromise listed
here, the recovery path through revocation list signing remains
available.

### 7.3 What is not mitigated

**Against A3 with sufficient access** — an adversary with GitHub
organization administrative access can disable branch protection,
remove reviewers from environment protection, modify workflows
without review, and produce a signed release whose per-product key
signature is cryptographically valid. The signature attests "this
was produced by a workflow on a tag in this repository under the
production keyring"; it does not attest "this was reviewed by the
intended approvers", because GitHub does not bind reviewer identity
into the signature.

**Against A4 with compromised reusable workflow not visible in the
local repository** — a workflow that references an external action
by mutable reference (`@main` rather than `@<sha>`) is vulnerable to
upstream tampering. The release-sign workflow must pin all action
references to immutable commit SHAs; this is a discipline matter, not
a property the platform enforces.

**Against A5 in full** — until hermetic builds and full image bit
identity are achieved (`SUPPLY_CHAIN.md` tracks both), an attacker
who can place malicious content in an upstream dependency can have
that content signed into a release. The signature is valid; the
content is malicious. Reproducibility, when fully achieved, allows
two independent builds to be diffed and discrepancies surfaced;
until then, this is not enforced.

**Against A6** — TactiQ Engineering has no visibility into the
GitHub-hosted runner internals beyond what GitHub publishes.
Self-hosting runners would shift the trust burden but introduce a
different set of compromise surfaces and require operational
infrastructure not currently in place.

### 7.4 What this means for consumers

A consumer verifying a TactiQ OS release per `VERIFY.md` validates
that the artifact was signed by the workflow identity bound to the
tag. This does not constitute verification of intent, of reviewer
approval, or of build hermeticity — those are operational properties
of the release process, not cryptographic properties of the
signature.

Consumers operating in threat models where this distinction matters
should:

- Verify multiple builds against each other (when reproducibility
  permits) before trusting a single release
- Maintain their own SBOM diffs across releases
- Monitor the revocation list and apply incident-driven updates
- Where deployment scenarios warrant, build TactiQ OS from source
  under their own keyring (the sovereignty-of-operator-keys
  principle in §1 explicitly supports this)

### 7.5 What this section does not cover

- **Formal attacker capability matrix in the security-architecture
  sense.** This section names categories of capability and what is
  mitigated, but does not provide formal attack trees, blast radius
  tables, or per-asset impact analyses. Formal security architecture
  documentation is a Phase 3+ deliverable; what is here is engineering
  honesty about the present state, not a substitute for that work.
- **Incident response playbooks.** What the team does on detection of
  any of A1–A6 is an operational document, not an architecture
  document. Tracked separately.

## 8. Catastrophic compromise recovery

This section names what happens when the signing path itself is
compromised, beyond what §7 covers — specifically, when the release
root or its custody is compromised. (Addresses review pt. 12.)

### 8.1 Three recovery scenarios

**Scenario 1: per-product key compromise.** The CI-materialized
per-product signing key is suspected of having been used by an
unauthorized party. Recovery procedure is in §2.4: revocation list
signed by the air-gapped release root, new per-product key signed
by the air-gapped release root, next release ships with the new key.

Field impact: devices in the field receive the revocation list as
part of the next update; they refuse subsequent updates signed by
the revoked key. OTP-burned platforms are unaffected — the OTP
encodes the release root hash, not the per-product key hash, so the
new per-product key is accepted by U-Boot upon validation through the
release root chain (§2.5). This scenario is recoverable through the
signing chain alone.

**Scenario 2: release root compromise on platforms without OTP burn.**
The release root itself has been used by an unauthorized party, or
its custody has been violated.

Recovery procedure: generate a new release root on a new air-gapped
host (the old one is considered untrusted); sign new per-product keys
under the new release root; update all consumers (this repository's
trust documents, downstream verifiers) to reference the new release
root fingerprint; deprecate the compromised release root by
publishing a deprecation notice signed by the new root.

Field impact on platforms without OTP burn: devices accept updates
signed under the new release root once their trust store is updated
to include the new release root fingerprint. This update itself must
be delivered through a trustworthy channel — out-of-band confirmation
of the new fingerprint, manual operator action, or an update
delivered through a channel the compromised release root does not
control. The bootstrap is non-trivial but recoverable.

**Scenario 3: release root compromise on OTP-burned platforms.** The
release root that is encoded in the OTP fuses of fielded devices has
been compromised. The OTP cannot be changed.

This is the catastrophic scenario. Recovery through the signing
chain alone is not possible: the compromised release root remains
the only entity U-Boot on these devices will trust, and the
compromised release root can sign updates that the devices will
accept.

The mitigation has two parts.

**Part 1: prevention.** OTP burn is gated on the release root having
reached a stable state — keys generated on hardware procured for the
purpose, custody documented and reviewed, multi-party access
procedure in place. The custody discipline aims to make Scenario 3
sufficiently unlikely that the platform can be operated.

**Part 2: physical recovery path.** A device-level mechanism that
allows installation of new firmware bound to a new release root,
authorized by physical presence rather than by signed update.
Concretely: a hardware jumper or button sequence at first boot that
puts the device into recovery mode; in recovery mode, the device
accepts a firmware image signed by a recovery root that is also
encoded in the OTP fuses alongside the primary release root.

The recovery root is held under stricter custody than the release
root (e.g. threshold-shared across founders and an external trustee
escrow), used only for Scenario 3 recovery, never used for ordinary
operations. This requires the OTP to encode two hash fields rather
than one, which is a hardware design decision that must be made
before OTP burn on the first generation of fielded devices.

**The decision on whether to include a recovery root in OTP is
product-level, not OS-level.** TactiQ OS supports either choice: the
boot chain accepts a U-Boot that validates against one OTP-fused key,
or one that validates against either of two OTP-fused keys. TactiQ
Box and OEM-built devices each make their own call.
The architectural recommendation is to include a recovery root; the
operational cost is one additional key under stricter custody, and
the alternative is field replacement of all OTP-burned devices on
Scenario 3.

### 8.2 What is not a recovery path

- **Revocation of the release root by the release root.** A revocation
  signed by the compromised root has no meaning against the same root.
- **Update delivered through the compromised signing chain.** By
  assumption, the chain is what is compromised.
- **Software-level recovery on OTP-burned devices.** The OTP is a
  hardware constraint that no software can override.

### 8.3 Long-term direction

**Threshold signing for the release root.** The strongest mitigation
against Scenario 2 and Scenario 3 is to require multiple independent
parties to co-sign release root operations. With (k, n) threshold
signing, compromise of fewer than k holders does not produce a valid
signature. This is operationally heavier than single-party signing
and is not specified for v0.2; it is named as the long-term direction
the keyring lifecycle is built to accommodate.

**The release root hierarchy in §2.1 is compatible with future
threshold signing.** Replacing single-party release root signing with
threshold signing does not require changes to the per-product key
flow or to OTP burn — only to the air-gapped signing host's
operational procedure.

## 9. Implementation order

The areas in §2–§6 have dependencies. In dependency order:

1. **§2.6** — Generate release root, first per-product key, configure
   CI secret. No other step is possible without this.
2. **§4** — Confirm no-initramfs posture; remove any latent
   `INITRAMFS_IMAGE` references; ensure storage and filesystem
   modules are built-in. This is a kernel config audit, not new
   work.
3. **§3** — FIT signing integration in Yocto build. U-Boot config
   update. CI workflow update to materialize the per-product key,
   sign FIT, and remove the key from the runner. First release tag
   under production keyring.
4. **§5** — RIM generation in the release pipeline. Schema published.
   First release with attached RIM. PCR matching semantics (exact /
   allow-list / event-log-replay) implemented in the verifier.
5. **§2.4** — Revocation list publication mechanism, even if no
   revocations have occurred. Needed before OTP burn becomes safe.
6. **§8.1 Part 2** — Recovery root generation and OTP layout decision.
   Decision must be made before OTP burn on first-generation fielded
   devices.
7. **§6** — Reconcile product-facing material with this document.
   Documentation edits, no engineering work.

After step 4, the boot chain in `BOOT_CHAIN.md` per-stage table moves
several rows from OFF to ON. After steps 5+6, OTP burn becomes
unblocked on a per-platform basis. After step 7, external positioning
is internally consistent.

This order is independent of attestation agent work in
`ATTESTATION.md` § "Implementation roadmap". The two roadmaps can
proceed in parallel.

## 10. What this document does not cover

- **TactiQ Edge and Box release integrity.** Each product
  maintains its own per-product key and its own release pipeline,
  under the same release root and following the same patterns.
  Product-specific deviations from these patterns are documented in
  each product's own repository.
- **Provisioning protocols.** How a verifier and an agent come to
  hold each other's trust roots at deployment time is a deployment
  concern, restated from `ATTESTATION.md` § "Verification protocol".
- **Operational key custody.** `KEY_CUSTODY.md` (not public) covers
  the release root storage, access, recovery procedure, and (when
  applicable) recovery root custody.
- **Certification.** Common Criteria, FIPS 140-3, or equivalent
  certification of the keyring management procedure is a long-horizon
  item documented in `Platform_Strategy` § "Roadmap".
- **Formal security architecture artifacts.** Attack capability
  matrices, blast radius tables, recovery timelines, incident
  playbooks, formal trust boundary diagrams — these are Phase 3+
  deliverables. v0.2 makes engineering decisions and documents
  them with the rigor appropriate to the present state of the
  project; it does not substitute for that future work.

## References

- `BOOT_CHAIN.md` — chain of trust from silicon root to attestation;
  Roadmap section names the boot chain steps that this document
  makes concrete.
- `SUPPLY_CHAIN.md` — supply-chain self-assessment; release-signing
  posture builds on the SLSA L2 source-archive provenance described
  there. Reproducibility state from this document is honestly
  reflected in §1.
- `KERNEL_HARDENING.md` — kernel hardening posture; § "Initramfs"
  names the gap that §4 of this document closes.
- `ATTESTATION.md` — attestation framework specification; RIM is the
  deliverable named in § "Implementation roadmap" step 4.
- `THREAT_MODEL.md` — consolidated adversary model; § 6 (Per-platform
  variations) is the source of the TPM class disclosure posture in
  §6 of this document.
- `VERIFY.md` — consumer verification procedure; Appendix B (tag-SAN
  binding) and § 4.1 (workflow identity) apply to every signature
  this document specifies.
- `recipes-bsp/u-boot/` — U-Boot recipe in the BSP layer; FIT-signing
  integration target.
- `recipes-core/rauc/` — RAUC keyring recipe; production keyring
  transition target.
- `recipes-kernel/linux/linux-yocto/tactiq-security.cfg` — kernel
  security fragment; TPM driver configuration.

## Appendix A — Changes from v0.1

This appendix lists the changes between v0.1 and v0.2, indexed to the
v0.1 review comments that prompted them.

**Review pt. 6 — PCR matching semantics.** §5 rewritten. v0.1
implied exact-byte PCR matching across PCR 0–10, which would produce
false positives in operation. v0.2 specifies per-PCR semantics:
allow-list for PCR 0–3, exact match for 4–9 where inputs are
reproducible under our control, event-log replay for PCR 10. §5.1
documents the policy and the qualification process for updating the
allow-list.

**Review pt. 7 — Adversarial CI threat model.** §7 added. v0.1 named
mitigations (required reviewers, tag triggers, restricted secrets)
without naming the adversary classes those mitigations addressed or,
importantly, what they did not address. §7 names six adversary
capabilities, what is mitigated, what is not mitigated, and what this
means for consumers operating in stronger threat models.

**Review pt. 8 — Hermetic build boundary.** §1 principle rephrased.
v0.1 stated "reproducibility over key trust" as if reproducibility
were an established cryptographic property; the current state per
`SUPPLY_CHAIN.md` is per-file content identity (99.943% byte
identity, hermetic builder absent). v0.2 states explicitly that the
chain is "signing-anchored with reproducibility as supporting
evidence" until full bit identity on a hermetic builder is achieved.

**Review pt. 9 — Air-gap vs Sigstore tension.** §1 principle
rephrased. v0.1 stated "air-gap compatibility" as if Sigstore
verification worked unconditionally offline. v0.2 specifies that
air-gap verification is possible "provided the verifier has
previously fetched the Sigstore trust bundle". The pre-fetched bundle
is a distributable artifact and is the basis for the offline
verification claim.

**Review pt. 10 — TPM class disclosure.** No change. v0.1 §6 was
endorsed by the review; preserved unchanged.

**Review pt. 11 — Formal security architecture.** §10 expanded to
name explicitly that formal artifacts (attack capability matrices,
blast radius tables, recovery timelines, incident playbooks, formal
trust boundary diagrams) are Phase 3+ deliverables and that v0.2
does not substitute for them. §7 contributes the engineering-level
threat model that approximates one component of this future work.

**Review pt. 12 — Catastrophic compromise recovery.** §8 added. v0.1
described revocation through the release root without addressing the
case where the release root itself is compromised, particularly on
OTP-burned platforms. §8 names the three recovery scenarios,
specifies the recovery root and physical recovery path for Scenario
3, and states the OTP layout requirement that follows from this. §9
adds the recovery root decision to the implementation order before
OTP burn.

**§2.5 correction.** OTP fuses encode the **release root** public
key hash, not the per-product key hash. v0.1 stated the latter, which
would have locked the platform to a single per-product key for life.
v0.2 corrects this; §2.5 specifies the OTP → release root → per-product
key validation chain.
