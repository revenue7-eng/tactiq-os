# Attestation framework

This document specifies the attestation framework toward which TactiQ
OS is built. It sits alongside `THREAT_MODEL.md` (consolidated
adversary model), `DESIGN_PRINCIPLES.md` (per-domain rationale),
`SUPPLY_CHAIN.md` (supply-chain self-assessment), `SECURITY.md`
(vulnerability disclosure policy), and `VERIFY.md` (consumer
verification procedure).

This is a v0.1 document. It iterates as the implementation matures.

Last reviewed: 2026-04-25.

## Status

The attestation framework specified here is the architectural target.
The current implementation status in v2.1.0-rc6 is a stub: the binary
installed at `/opt/tactiq/bin/tactiq-agent` is a placeholder
(`recipes-core/tactiq-agent/files/tactiq-agent-stub.sh`) that holds
the systemd unit, SELinux domain, vault directory layout, and TPM
device access permissions in place while the real implementation is
built.

What exists in v2.1.0-rc6 is the supporting infrastructure: kernel
TPM drivers compiled in, IMA machinery enabled at PCR 10, SELinux
domain (`tactiq_agent_t`) with permissions to access the TPM device
nodes through the `tactiq_tpm_access` interface macro (defined in
`meta-tactiq-selinux/policy/modules/services/tactiq_tpm.if`; it grants
read/write on `/dev/tpm0` and `/dev/tpmrm0` and append on
`tpm_log_t`-labelled kernel TPM event log files), vault domain
(`tactiq_vault_t`) for sealed key material, and the build-identity
manifest at `/etc/tactiq-release` written by the `tactiq-release`
recipe. These are the parts that an attestation agent will use; the
agent itself is not yet there.

This document describes what the agent is being built toward. It
deliberately separates design from implementation status so that a
reader of this repository can see the architecture without confusing
it with the current state.

## Design goals

The framework is built to satisfy five properties simultaneously,
because dropping any of them would weaken the position TactiQ OS is
designed to occupy.

**Hardware-rooted.** Cryptographic operations bound to TPM-held key
material rather than software-held secrets. The strength of this
binding varies with TPM class — discrete TPM provides hardware
isolation, firmware TPM (fTPM) provides software isolation in the
SoC's secure-world TEE. Per-platform variation is documented in
`THREAT_MODEL.md` section 6.

**Offline-capable.** The framework operates without continuous
connectivity to a cloud service, external CA, OCSP responder, or NTP
source. Trust is established through pre-provisioned material;
freshness is anchored in TPM-resident state rather than network
time.

**Anti-replay.** A captured attestation message cannot be replayed
later by an adversary on the network or by a compromised peer. The
freshness mechanism is hardware-enforced rather than relying on
clock synchronization.

**Fail-closed.** Attestation failure has consequences. The semantics
of what happens when an attestation cycle fails — local logging,
network isolation, service halt — are part of the framework design,
not an operational afterthought.

**Verifier-independent.** Any party with the correct trust roots and
a reference verifier implementation can validate an attestation. No
hidden cloud service, no proprietary verification endpoint.

## Attestation payload

An attestation message is a signed structure containing the
following fields.

**Device identity.** The Ed25519 public key fingerprint of the
agent's signing key. This is the long-term identity of the device
within the attestation framework. Created at first boot, persists
across reboots, sealed to the TPM (see Key management).

**Build identity.** The contents of `/etc/tactiq-release` as written
by the `tactiq-release` recipe — version, codename, UTC build date,
machine target, meta-layer git short hash, image basename. This is
what allows a verifier to correlate a running attestation with a
specific build artifact whose provenance is independently verifiable
through the supply-chain machinery described in `SUPPLY_CHAIN.md`.

**Measured platform state.** A TPM quote over the relevant Platform
Configuration Registers — boot-time measurements (PCR 0–7), kernel
and initramfs (PCR 8–9), IMA runtime measurements (PCR 10).
Inclusion of the quote is what turns the attestation from a
self-declaration of userspace into a hardware-anchored statement of
platform state. This is the integration that the boundary statement
in `DESIGN_PRINCIPLES.md` and `THREAT_MODEL.md` refers to.

**Freshness.** A monotonic counter value drawn from a TPM
non-volatile index, atomically incremented at the start of each
attestation cycle. See Freshness mechanism below.

**Local timestamp.** The wall-clock time at attestation generation,
recorded for logging and correlation. Not used as a freshness
mechanism — wall-clock time is unreliable across offline operation.

**Signature.** Ed25519 signature over the canonical serialization of
the above, produced by the agent's signing key inside the TPM
(non-exportable private key, signing performed by the TPM itself).

## Key management

The agent's Ed25519 signing keypair is generated within the TPM at
first boot, parented under the platform endorsement key. The private
half is non-exportable — every signature operation is performed by
the TPM, the host never sees the private key in memory.

The keypair is sealed to a PCR policy that binds usability to the
expected boot-time measurements. A device booted into an unexpected
state cannot use the signing key — the TPM refuses the operation
because the PCR values do not match the sealing policy. This is what
makes the attestation refuse to lie when the platform has been
modified: a tampered boot chain cannot produce a valid signature
because the key is not available to the modified state.

Public keys, certificates, and per-peer trust state live in the
`tactiq_vault_t` SELinux domain. The vault is the only domain with
read-write access to long-lived attestation state.

## Freshness mechanism

Attestation messages must be replay-resistant in a setting where
freshness sources commonly assumed by other protocols are not
available. NTP-synchronized clocks drift over offline operation;
challenge-response with verifier-supplied nonces requires a server
to issue nonces in the first place.

The framework uses a TPM non-volatile monotonic counter
(`TPM2_NV_Increment`) as the primary anti-replay primitive. Before
each attestation cycle the agent atomically increments the counter
from N to N+1 and includes N+1 in the signed payload. The verifier
maintains the highest counter value it has accepted from each known
device. Any incoming attestation whose counter is less than or equal
to the previously-accepted value is rejected as replay.

The TPM hardware enforces three properties of the counter that make
this work: it can only increase, it cannot be set to an arbitrary
value, and it survives reboots in non-volatile storage. The counter
range (2^64) is large enough that exhaustion is not a concern at any
realistic attestation rate.

Verifier-supplied nonces are an optional second layer for
interactive scenarios where they are available. The base protocol
does not require them.

## Verification protocol

The base protocol is pull-mode: the verifier initiates the
attestation cycle, not the agent.

1. The verifier opens an mTLS 1.3 connection to the agent. Both
   sides authenticate through pre-provisioned X.509 certificates
   bound to TPM-resident Ed25519 keys. There is no certificate
   authority in the path; trust is established through direct
   exchange of certificates at provisioning time and stored in the
   peer's vault.

2. The verifier optionally sends a nonce. The agent reads the TPM
   monotonic counter, increments it, generates the attestation
   payload (including the new counter value, a TPM quote over the
   relevant PCRs, and the build identity), signs it, and returns it
   over the mTLS channel.

3. The verifier validates: signature is valid against the known
   device public key; counter is strictly greater than the last
   accepted value for this device; PCR values match the expected
   reference values for this build identity; build identity matches
   an expected build artifact whose provenance can be independently
   verified.

4. On success, the verifier updates its `last_accepted_counter`
   record. On any failure, the attestation is rejected and the
   failure is logged.

Initial trust establishment — how a verifier and an agent come to
hold each other's certificates in the first place — is a deployment
concern. The base framework assumes pre-provisioned trust;
deployment-specific bootstrap protocols are documented separately.

Revocation is local: removing a device from the verifier's trust
store, or removing the verifier from the device's trust store, is
sufficient. There is no global CRL, no OCSP responder, no shared
revocation infrastructure to maintain.

## Reference verifier

An attestation framework is incomplete without a reference verifier
implementation that consumers can use to validate attestations
independently. The reference verifier is part of the attestation
framework scope and is tracked as a deliverable alongside the agent
itself.

The reference implementation will be a small Go program, MIT
licensed, in this repository or a sibling repository under the same
organization. It will validate the components of the attestation
payload as described above. Without it, attestations can be produced
but cannot be independently consumed; with it, the framework
supports end-to-end verification by any party with the correct trust
roots.

## What attestation does not prove

The framework, even when fully implemented, has explicit limits.
Stating them is part of the documentation, not an oversight.

**In the current v2.1.0-rc6 stub state.** Nothing. The binary at
`/opt/tactiq/bin/tactiq-agent` does not produce attestations. The
SELinux policy, systemd unit, and TPM access primitives are in
place; the agent that uses them is not. Any document describing
attestation produced by TactiQ OS today is describing an unbuilt
target, not a running system.

**Once the real agent is implemented but before TPM quote
integration is complete.** The agent will be able to sign payloads
with its TPM-resident key, but the payloads will reflect what
userspace declares about the platform state, not what the hardware
measured. This is the boundary called out in `DESIGN_PRINCIPLES.md`
and `THREAT_MODEL.md`: the difference between "the agent signs" and
"the system proves what it ran." A consumer of attestation in this
intermediate state should treat it as authenticated build-identity
self-declaration, not as a hardware-measured statement of platform
state.

**On platforms with firmware TPM rather than discrete TPM.** The
cryptographic root of trust is software-anchored in the SoC's
secure-world TEE. The strength of the attestation is bounded by TEE
isolation guarantees rather than hardware isolation. See
`THREAT_MODEL.md` section 6 for the per-platform variation in
detail.

**Compromise of provisioned trust.** If the verifier's certificate
store has been tampered with, or if the agent's vault has been
compromised before the agent's TPM-resident keys were sealed, the
framework cannot detect this from attestation alone. Initial
provisioning is the trust anchor; subsequent operations build on it
but do not validate it.

**Workload-level integrity.** The framework attests the platform
state. It does not attest what a workload running on the platform
does at runtime. Workload integrity (model authenticity, inference
correctness, data handling) is an application-layer concern, not an
OS-layer attestation concern.

## Implementation roadmap

The work to bring the framework from current stub state to the
specification above falls into roughly four pieces, in dependency
order.

1. **Real agent binary.** Replace `tactiq-agent-stub.sh` with a Go
   implementation that creates the keypair on first boot, generates
   the attestation payload structure described above, signs it with
   the TPM-resident key, and serves the verification protocol over
   mTLS. Without TPM quote at this stage; the agent attests
   userspace state.

2. **TPM quote integration.** Add the TPM quote over PCRs 0–10 to
   the attestation payload. This is the integration that closes the
   declaration-vs-measurement boundary.

3. **Reference verifier.** Implement and publish the verifier as
   described above.

4. **Reference Integrity Manifest (RIM) generation.** Produce
   per-build expected-PCR manifests as part of the release pipeline,
   so verifiers can validate attestations against known-good
   measurements without each verifier independently determining
   what to expect.

Each step is independently shippable. Each is tracked separately as
the work progresses.

## References

- `THREAT_MODEL.md` — consolidated adversary model and per-platform
  variation.
- `DESIGN_PRINCIPLES.md` — per-domain rationale, including the
  attestation principle and current-state summary.
- `SUPPLY_CHAIN.md` — build provenance and release-artifact signing
  posture, which the build-identity field of the attestation payload
  ties into.
- `recipes-core/tactiq-agent/` — current agent recipe (stub).
- `recipes-core/tactiq-release/` — build identity manifest writer.
- `recipes-kernel/linux/linux-yocto/tactiq-security.cfg` — kernel
  TPM and IMA configuration.
- `meta-tactiq-selinux` — SELinux policy modules including
  `tactiq_agent_t` and `tactiq_vault_t` domains.
