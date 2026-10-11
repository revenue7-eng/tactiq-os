# General availability gates: TactiQ OS v2.1.0

This document defines when TactiQ OS v2.1.0 may be released without a
release-candidate suffix. It applies to the reference platform, Radxa
Rock 5A (RK3588S) with a discrete SPI TPM 2.0.

A release candidate may ship with any known issue, provided the issue is
disclosed in the release's coverage manifest
(`security/coverage-rock5a.<tag>.yaml`, section `known_issues`). General
availability may not. Each gate below names the known issue it closes by
its manifest id. A gate is closed when the coverage manifest of the
release lists that id under `resolved` and names the evidence given
here. A gate is never closed by a statement in prose, in this document
or elsewhere.

No dates are attached to the gates, and the list implies no order of
work. Where a gate depends on another, the dependency is stated.

Some properties are classed as **disclosed at GA**: properties of the
reference platform that a release cannot remove. They may remain open at
GA if the release's RIM and coverage manifest disclose them.

---

## 1. Boot chain anchored in hardware

**G1. SPL is authenticated by the BootROM** (`spl-unmeasured-otp`).
Closed when the release-root public key hash is fused into RK3588 OTP on
the reference device, the BootROM refuses an SPL not signed under it, and
the reference values describe the chain from the BootROM on. The key
arrangement is fixed in `RELEASE_INTEGRITY.md` section 2.5. Evidence: the
fusing procedure, published; the serial-console log of a refused
unsigned SPL and of an accepted signed one, on the fused device.

**G2. Release PCR values are observed, not computed**
(`pcr-computed-not-observed`). Closed when the final PCR values of the
release loader and release image are read from a device running them
and match the published reference, both after a power cycle and after
a warm reboot. Depends on G1 for the values to start at the BootROM.
Evidence: the PCR read, the event log and a signed quote pair across a
warm reboot from the release device, attached to the release.

## 2. The release image carries the protections the development image has

**G3. IMA appraisal in the release image** (`ima-off-production`).
Closed when `tactiq-image` applies the IMA policy and signatures and
boots with appraisal enforced, and the coverage manifest states the mode
observed on the device. Evidence: the policy shipped in the image and
the board-state record of the release device.

**G4. The running root filesystem is verity-protected**
(`rootfs-not-verity`). Closed when the release image boots its root
through dm-verity with the root hash carried in the signed slot device
tree, and a
modified root block is refused on the device. Evidence: the board-state
record and the refusal log.

## 3. Known vulnerabilities

**G5. No high-severity vulnerability left in an open state.** Every
high-severity CVE matched against the image is either fixed or carries a
published VEX statement (`not_affected` with a justification, or
`fixed`), so none remains `affected` or `under_investigation`. This is
the "CVE to zero" gate stated in the coverage manifest under EX-0009.
Evidence: the enriched CVE report and the VEX document of the release.

**G6. The CVE scan states its own inputs** (`cve-db-date-rust`). Closed
when the release records the date of the CVE database used and checks
the crate dependencies of the Rust packages. Evidence: the CVE report
provenance fields.

## 4. Updates on a device without a clock

**G7. Update acceptance does not depend on a correct wall clock**
(`no-rtc`). Closed when a release device with no time source installs a
validly signed bundle published after the device's own release, and
refuses a bundle with a lower version. The clock floor at the release
date and the version limits are introduced in v2.1.0-rc14; the remaining
case is a bundle whose signer certificate is newer than the floor.
Evidence: both installs, on the device, without setting the clock by
hand.

## 5. Evidence a third party can check

**G8. The layer set is proven, not asserted** (`layer-set-evidence`).
Closed when the release carries the output of
`scripts/check-layers.sh --check` run against the assembled layer set
before the build. Evidence: that output, listed in `SHA256SUMS`.

**G9. A third party has rebuilt a release** (`independent-rebuild`).
Closed when a published procedure names which unsigned artifacts a
rebuild is compared on, and a party other than TactiQ AI has followed it
and published the result. Evidence: the procedure in
`INDEPENDENT_VERIFICATION.md` and the third party's report.

**G10. An attestation from a release device verifies against the RIM**
(`no-attestation-envelope`). Closed when a signed envelope produced on a
device running the release, after a power cycle, verifies against that
release's signed RIM by the published procedure. Depends on G2.
Evidence: the envelope, the verification output and the procedure.

**G11. A release device can be registered** (`ak-registration-bench-only`).
Closed when the AK of a device that runs the release image can be
registered against its EK certificate without the development image,
and the record is signed by the Registration Signer and time-stamped
(RFC 3161, the record format after `tactiq-ak-registration/1`).
Evidence: the record of a release device and its verification.

## 6. The attestation agent on a long-running device

**G12. Agent evidence is bounded** (`agent-evidence-unbounded`). Closed
when the NV counter wear and the audit directory have a stated bound
that holds for the device's service life. Evidence: the bound and the
mechanism, in `ATTESTATION.md`.

**G13. The agent's skip switch works as documented**
(`agent-skip-switch-unseen`). Closed when systemd can see the switch
under the release policy, or the switch is removed. Evidence: the
policy rule or the removal, and a boot with the switch present.

## 7. Documents match the implementation

**G14. Attestation documents describe what is built**
(`attestation-docs-stale`). Closed when `ATTESTATION.md` and
`THREAT_MODEL.md` describe the implemented agent and envelope.
Evidence: the documents at the release tag.

---

## Disclosed at GA

**TPM reset line.** SPL pulses the TPM reset line before measuring, so a
warm reboot starts the TPM like a power cycle (`security/rim-disclosures-rock5a.txt`).
The line is a GPIO that the running system can also drive, so a TPM
reset is not by itself evidence of a reboot. This is a property of the
board. It stays open at GA if the RIM states it. That the release loader
resets the TPM on a warm reboot is not yet observed; observing it is part
of G2. The coverage manifest id `tpm-not-reset-warm-reboot` of
v2.1.0-rc13 predates this disclosure and is superseded by it.

---

## Changing this list

A gate is added when a known issue is found that a release for operators
cannot carry. A gate is removed only with the reason recorded in the
commit that removes it. The list is versioned with the repository; the
version that applies to a release is the one at its tag.
