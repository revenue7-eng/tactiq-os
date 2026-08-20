# Design commitments

This document records product invariants: constraints that bind every
release from the first line of the code they govern. It is not a
roadmap. A roadmap item is done once; a commitment holds on every
release, and is checked on every release. It sits alongside
`DESIGN_PRINCIPLES.md` (per-domain rationale and current state),
`RELEASE_INTEGRITY.md` (release signing and verification chain), and
`SUPPLY_CHAIN.md` (supply-chain self-assessment).

Changes to this file are deliberate and visible: any edit that
weakens or removes a commitment requires sign-off from both founders
and is stated in the release notes of the release that ships under
the changed text. Commitments are announced here before they take
effect, never discovered in the field.

Status vocabulary: a commitment marked *pre-implementation* is
adopted before the code it constrains exists; its verification
criterion becomes a release gate when the first release of that code
ships.

Last reviewed: 2026-08-19.

## DC-1: Removal test — survivability without vendor

*Adopted 2026-08-19. Pre-implementation: binds every TactiQ Edge
release from the first.*

A customer who terminates the relationship with the vendor keeps a
working device.

**Invariant.** Any device capability that operated without TactiQ
Edge continues to operate without TactiQ Edge. Any capability that
operated without an active Doctrine Updates subscription continues
to operate after subscription lapse. Capabilities whose nature
requires delivery of new artifacts (new doctrine versions, remote
support) are outside this invariant by definition: lapse freezes
doctrine at the last delivered version and stops delivery. It does
not degrade or disable what is already deployed.

**New capabilities.** A capability may depend on an active
subscription only where the dependency follows from its nature —
it requires delivery. A subscription dependency introduced as a
control mechanism violates this commitment.

**Working device, defined.** The device boots and performs its
last-configured function on the last-delivered artifacts.

**Mechanism constraints.** The base layer and deployed artifacts
contain no license servers, no phone-home, no time-bomb or expiry
mechanisms. The proprietary layer's value lives in delivery of
updates, tooling, and support; deployed functionality is not
collateral.

**Verification criterion.** Two independent negative tests, on real
hardware, per TactiQ Edge release:

1. *Edge removal.* Remove or disable all TactiQ Edge components;
   power-cycle. The device boots and the existing configuration
   performs its function.
2. *Subscription lapse.* Simulate expired or absent subscription
   state; power-cycle. The device boots and the existing
   configuration performs its function on frozen doctrine.

The scenarios are tested independently because they are independent
failure paths. A release that fails either test does not ship.

A passing result is itself a dated claim and decays: each recorded
run carries its date, and a release claim is only as fresh as the
latest passing run — min(dated commitment, freshest passing test).
The commitment caps what a test may claim; the test caps what the
commitment may claim. (Formulation due to Shyan-Ming Perng.)

## DC-2: Open/proprietary boundary shifts are announced, not discovered

*Adopted 2026-08-19.*

The boundary between TactiQ OS (open, MIT) and the proprietary layer
above it is a published fact of the platform. It may move — but never
silently.

**Invariant.** A capability shipped in a TactiQ OS release under the
open license is not withdrawn into the proprietary layer, and its
maintenance is not discontinued in favor of a proprietary
replacement, without a change to this file landing before the release
that implements the shift. The record here precedes the shift; users
learn of a boundary change from this document, not from a changelog
diff or a stalled repository.

**Scope note.** This commitment governs the visibility of boundary
changes, not the licensing roadmap itself. License evolution of
TactiQ OS is a separate decision recorded in `LICENSE` and release
notes when and if it occurs.

**Verification criterion.** Reviewable from git history alone: for
any release moving a previously-open capability behind the
proprietary boundary, a commit to this file predates the release
tag. Absence of such a commit alongside such a shift is a defect in
the release.

## DC-3: No vendor-initiated egress from the base layer

*Adopted 2026-08-19.*

The device does not call home. This restates, as a binding
commitment, a property the architecture already carries: attestation
is pull-mode — the verifier initiates, never the agent
(`ATTESTATION.md` § Verification protocol) — and update delivery is
channel-independent with offline delivery as the assumed default
(`SUPPLY_CHAIN.md` § Update channel).

**Invariant.** The base layer initiates no network connections to
vendor infrastructure: no telemetry, no usage reporting, no
license or activation checks, no automatic update polling toward
vendor endpoints. Any egress of data from the device is an explicit
operator action or an operator-configured service. Operator-directed
traffic (NTP, DNS, update mirrors under operator control) is outside
this invariant: the constraint is the destination and the initiator,
not the existence of a network stack.

**Verification criterion.** Negative test on real hardware, per
release: a device at rest — booted, idle, network up, no operator
action — produces zero packets addressed to vendor-controlled
endpoints over the observation window, verified by traffic capture
external to the device.

## DC-4: No long-lived trust in the vendor's signing authority

*Adopted as a design principle in `RELEASE_INTEGRITY.md` §1
("Sovereignty of operator keys"); recorded here as a commitment.*

**Invariant.** No part of the release integrity chain requires trust
in TactiQ Engineering as a long-lived signing authority. An operator
rebuilding from source under their own keyring produces a
functionally identical chain. The default keyring is the production
reference, not the only permissible root.

**Verification criterion.** The consumer-side procedure is
`INDEPENDENT_VERIFICATION.md`: a third party with no access to the
build host and no relationship with the project verifies that a
published release corresponds to the source, and can rebuild under
their own keys. Divergences outside the release's documented
exception list are findings under that document's §4.

## What this document does not cover

- **Hardware survivability boundary for TactiQ Box.** The minimal
  functionality of the physical product after vendor termination,
  and the mechanisms that could prevent it, are a product-level
  question tracked separately; DC-1 covers the software stack.
- **Licensing roadmap.** DC-2 governs visibility of boundary
  shifts, not license evolution itself.
- **Operational procedures.** How the release gate executes the
  DC-1 and DC-3 negative tests (fixtures, capture setup, pass
  records) is release-pipeline documentation, not part of the
  commitment text.

## References

- `DESIGN_PRINCIPLES.md` — architectural principles and current
  state per domain.
- `RELEASE_INTEGRITY.md` — keyring hierarchy, FIT signing, RIM;
  source of the operator-key sovereignty principle behind DC-4.
- `SUPPLY_CHAIN.md` — supply-chain posture; update-channel delivery
  model behind DC-3.
- `ATTESTATION.md` — attestation framework; pull-mode protocol
  behind DC-3.
- `INDEPENDENT_VERIFICATION.md` — third-party verification
  procedure; verification path for DC-4.
