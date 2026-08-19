# TactiQ Design Commitments

Invariants, not milestones. Each commitment binds every release
from the first line of code onward. Changes to this file are
deliberate, visible, and require sign-off from both founders.

## DC-1: Removal Test (survivability without vendor)

*Adopted: 2026-08-19 · Status: design commitment (pre-implementation)*

**Invariant (preservation form):** any device capability that
operated without TactiQ Edge continues to operate without TactiQ
Edge; any capability that operated without an active Doctrine
Updates subscription continues to operate after subscription
lapse. Capabilities whose nature requires delivery of new
artifacts (new doctrine versions, remote support) are outside
this invariant by definition: lapse freezes doctrine at the last
delivered version and stops delivery — it never degrades or
disables what is already deployed.

**New capabilities:** a capability may depend on an active
subscription only where the dependency follows from its nature
(it requires delivery), never as an introduced control mechanism.

**Working device (definition):** the device boots and performs
its last-configured function on the last-delivered artifacts.

**Mechanism constraints:** no license servers, no phone-home, no
time-bomb or expiry mechanisms in the base layer or in deployed
artifacts. Edge's proprietary value lives in delivery of updates,
tooling, and support — never in holding deployed functionality
hostage.

**Verification criterion — two independent negative tests, on
real hardware, per TactiQ Edge release:**

1. *Edge removal:* remove/disable all TactiQ Edge components →
   power-cycle → device boots and the existing configuration
   performs its function.
2. *Subscription lapse:* simulate expired/absent subscription
   state → power-cycle → device boots and the existing
   configuration performs its function on frozen doctrine.

A release that fails either test does not ship.
