# Development image: owner and lockout authorization of the reference TPM set, what a process without them can no longer do (2026-11-26)

## Questions

1. With the owner and lockout authorization set on the reference TPM, does a
   process that can use the TPM but holds neither value get refused when it
   tries to evict the AK or the SRK, delete either counter, define an NV index,
   move the TPM clock forward, or set another owner value?
2. Does everything the device does at run time keep working without the
   values: the persistent handles, reading both counters, the agent, the stop
   service and the gateway, and a key created under the SRK and certified by
   the AK (the path of the TPM-bound key in `tpm-bound-key-dev-20261125.md`)?

## Why

`security/coverage-rock5a.v2.1.0-rc14.yaml` carries `tpm-owner-auth-empty`:
with the owner authorization empty, a process that can use the TPM can evict
the AK and take the device out of attestation until it is registered again.
On TactiQ OS the domains with TPM access are the attestation agent, the stop
service, vault and tamper. That forges nothing, but a compromised one of them
can destroy the device's registered identity. The stop design already survives
a redefined stop index, and a redefined counter cannot roll back; what the owner
authorization adds is that the identity, the counters and the TPM clock are out
of reach of such a process.

## Setup

- Board: the Rock 5A reference board, Infineon SLB9670, firmware 7.87.19691.2
  (login banner). Cold start: power removed with a flash drive inserted, then
  power on. The console shows `SPL measure: TPM reset`, slot B, and
  `TPM: platform hierarchy disabled` from the loader in the same boot. State
  block: `SELINUX Enforcing`, `IMA appraise-rules=4 measure-rules=8
  cmdline=none`, `ROOT root=/dev/dm-0`, `DM rootfs`, `SLOT B`. Development
  image in slot B, the build of `tpm-bound-key-dev-20261125.md`; the slot was
  not written in between.
- Before the change: `ownerAuthSet 0`, `endorsementAuthSet 0`,
  `lockoutAuthSet 0`, `disableClear 1`, `inLockout 0`; persistent handle
  `0x81010100` (the registered AK) only; `0x1500016` (epoch) and `0x1500017`
  (stop) defined as counters, `authwrite|authread`.
- tactiq-attest at `bb46a2a` (#38) adds `tactiq-agent close-owner`. The agent
  in this image predates it, so the same sequence was run with tpm2-tools by
  hand: persist the SRK, set the owner, then the lockout authorization, check
  the flags and probe the owner hierarchy. The command itself was run on a
  software TPM (`close-owner-swtpm.log`, below).
- Values: 32 random bytes each, generated on the board with `tpm2_getrandom`
  into `/tmp` (tmpfs), never printed, copied to the flash drive and compared
  there by SHA-256 before the change, removed from the board after it. The
  console shows their SHA-256 only. They are kept off the device by TactiQ.

## Steps on the board

```
tpm2_createprimary -C o -g sha256 -G ecc256:aes128cfb -c /tmp/co/srk.ctx
tpm2_evictcontrol -C o -c /tmp/co/srk.ctx 0x81000001
tpm2_changeauth -c owner file:/tmp/co/owner.auth
tpm2_changeauth -c lockout file:/tmp/co/lockout.auth
```

## Results

| check | result |
| --- | --- |
| SRK at `0x81000001` | persisted, `fixedtpm|fixedparent|sensitivedataorigin|userwithauth|restricted|decrypt` (`0x30072`) |
| TPM_PT_PERMANENT after | `ownerAuthSet 1`, `lockoutAuthSet 1`, `endorsementAuthSet 0`, `inLockout 0` |
| owner primary without the value | refused, `0x9A2` |
| owner primary with the value | works |

Without the values, each attempt refused with `0x9A2`, "authorization failure
without DA implications":

| attempt | rc |
| --- | --- |
| evict the AK `0x81010100` | 1 |
| evict the SRK `0x81000001` | 1 |
| delete the epoch counter `0x1500016` | 1 |
| delete the stop counter `0x1500017` | 1 |
| define an index `0x1500099` | 1 |
| move the TPM clock 600 s forward | 1 |
| set another owner value | 1 |

Kept working without the values:

| check | result |
| --- | --- |
| persistent handles | `0x81000001`, `0x81010100` |
| epoch and stop counters read | `0x2020`, `0x1fd3` (stop value odd: stopped; not read before the change) |
| `tactiq-agent`, `tactiq-stop`, `agentgateway` | active |
| P-256 signing key created and loaded under the SRK, certified by the AK | rc 0 each |

The `0x9A2` code also shows that a failed owner authorization does not count
toward dictionary-attack lockout on this TPM. The lockout hierarchy was not
probed with a wrong value, because a failed lockout authorization locks it; its
state is read from `lockoutAuthSet`.

## close-owner on a software TPM

`close-owner-swtpm.log` is the full output of `tests/close-owner/run.sh` at
tactiq-attest `bb46a2a`, then of the same script with `--no-close`. The first
run ends with `RESULT: all checks held`, the second with `RESULT: FAILED`: the
refusals checked there are the ones above, and without the command each of
them fails.

## What this does not show

- The board sequence was run by hand. `tactiq-agent close-owner` has run on a
  software TPM only; its first run on this board waits for an image whose
  agent includes `bb46a2a`.
- The endorsement authorization stays empty. The EK and the AK are created
  under it, and a key someone else makes there is not registered.
- This covers the reference device. A release device has no provisioning step
  that runs `close-owner`, so `tpm-owner-auth-empty` still holds for release
  devices.
- A process with TPM access can still use the AK: quote, and certify keys it
  creates under the SRK. Binding a key to the workload that should use it is a
  key policy, not the owner authorization.
- Where the values are kept and who holds them at a handover is decided with
  the device registration procedure, not here.

## Horizon

Holds while the owner and lockout values set here are in force. A rotation
(`close-owner` with the values in force), a TPM clear, or a TPM firmware update
means running these checks again.

## Files

`tpm-owner-closed-dev-20261126/`: `board-console-close-owner.log` (the PuTTY
scrollback from power on to `umount`), `close-owner-swtpm.log`.
