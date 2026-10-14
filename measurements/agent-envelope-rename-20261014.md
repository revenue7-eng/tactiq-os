# Atomic envelope write on the reference device (2026-10-14)

The agent at tactiq-attest `d2f6efc` (#251) writes each file of an
envelope as `<name>.part`, fsyncs it, renames it into place, writes the
`.tag` last and fsyncs the directory. This record covers its first runs on
the reference Radxa Rock 5A: a refusal by SELinux on the policy the
development image carried, the run after the policy fix, and a power cut
while the agent was running. It is the measurement behind the policy change
in tactiq-os-selinux #31 and the lock change in #254, and the board
evidence for the known issue `agent-envelope-not-atomic` in
`security/coverage-rock5a.v2.1.0-rc14.yaml`.

## What ran

| Item | Value |
|------|-------|
| Device | Radxa Rock 5A, development loader (FIT key `dev-fit`), console on UART ttyS2 |
| Agent | tactiq-agent from tactiq-attest `d2f6efc18512385173a4db91c4ecc4354036ab8b` (recipe `tactiq-agent_0.1.1.bb`, #251) in both images below |
| Slot A, before the fix | development image built on 2026-10-14 (label `20261014051711`) with tactiq-os-selinux `c2f49fa880c0c400815fe4802c13868b75c5a45b`, policy module `tactiq_agent` 2.4.2. Written to the device in maskrom as a full `.wic`. The tactiq-os commit of that build is not recorded here. |
| Slot B, after the fix | development image `20261014182518`, built from tactiq-os `07577f7c99c30d4bbe821a47ad05f28fb57eaec4` (#254) with tactiq-os-selinux `c3f7044fe3e390dd2c0752324a51feb506aa3eaa` (#31), policy module `tactiq_agent` 2.4.3. Boot partition sha256 `59d82eb6240727139a27fe4411bb05b52992c7e3660aad519b9608c64f83ea72`, rootfs (`.ext4.verity`) sha256 `3619888d99645df6aaf3835506625da6bc134eb82dc1bcaf9c927361af0f773f`, both written with `dd` from slot A and read back |
| Tools | tpm2-tools 5.8, BusyBox 1.37.0 on the device |
| Data partition | blank `/data` from the `.wic`; the device identity was restored into it as described below |

## Sources

All raw files are under `logs/`. They were copied from the terminal
(PuTTY for the device, WSL for the build host) into the session and kept
as pasted. Where a file joins two pastes of the same run, the repeated
prompt line between them shows the join.

| File | What it is |
|------|------------|
| `logs/agent-envelope-rename-20261014-slota-uart.log` | First boot of slot A after the maskrom write, power-on to login. The agent fails at boot (line 879). |
| `logs/agent-envelope-rename-20261014-identity.log` | Why the agent failed (`cannot run: Absent`), the AK handle in the TPM, the public area read back from it, and the same file in the `/data` image taken from the device before the write. |
| `logs/agent-envelope-rename-20261014-denied.log` | Identity restored, the agent started on policy 2.4.2: its status, the AVC records, the audit directory. |
| `logs/agent-envelope-rename-20261014-slotb-uart.log` | One console session: boot of slot A, write and read-back of slot B (lines 922 to 937), `rauc status mark-active other` (line 940), power-off, boot of slot B (line 1185 onwards). |
| `logs/agent-envelope-rename-20261014-running.log` | Slot B, policy 2.4.3: agent status, AVC records, audit directory after six minutes. |
| `logs/agent-envelope-rename-20261014-powercut.log` | Slot B after power was removed while the agent was running and then restored. |

## Observations

**The agent refuses to run without an identity (identity log).** On the
blank `/data` the agent exits with `cannot run: Absent` three times and
systemd stops the unit. `Absent` is the state in which neither
`/data/tactiq/keys/device_id` nor `/data/tactiq/keys/ak.pub` exists. The
AK stayed in the TPM across the image write: `tpm2_getcap
handles-persistent` lists `0x81010100`, the agent's default handle.

**Identity restored, not re-provisioned (identity log).** `tpm2_readpublic`
of `0x81010100` written to a file has sha256
`7305eb2f5c44527681eefff026fcfbd86a98ecbe0565a2b12c721ecd3d4a04bd`, the
same as `ak.pub` in the `/data` image taken from the device before the
write, whose `device_id` is `TACTIQ-BENCH-001`. The two files were put
back with the owner and modes the agent uses (`device_id` 0600, `ak.pub`
0644, owner `tactiq-agent`) and relabelled with `restorecon`. The AK the
registration record of `TACTIQ-BENCH-001` names is the one in the TPM; no
new key was made.

**Refused by SELinux on policy 2.4.2 (denied log).** The agent starts,
writes the four `.part` files of an envelope and stops at the first rename:
status `attest failed: rename /data/tactiq/audit/135744454656.msg:
Permission denied (os error 13)`. The kernel logs `avc: denied { rename }`
for `scontext=system_u:system_r:tactiq_agent_t:s0`,
`tcontext=system_u:object_r:tactiq_agent_audit_t:s0`, `tclass=file`,
`permissive=0`, once per attempt (three attempts). Module 2.4.2 grants the
agent `create read write open getattr setattr lock unlink` on
`tactiq_agent_audit_t` files and no `rename`. After the refusals the audit
directory holds only the four `.part` files of the last attempt, no file
under a final name: the failed envelope is not visible to a reader, and
the `.part` files of the two earlier attempts were removed by the next
attempt.

**Runs on policy 2.4.3 (running log).** Module 2.4.3 adds `rename` on
`tactiq_agent_audit_t` files and nothing else (tactiq-os-selinux #31). On
slot B the agent is `active (running)` and logs an envelope every 30
seconds with consecutive counter values
`135945781252` to `135945781261`. `dmesg | grep -i avc` prints nothing.
The audit directory holds envelopes `135945781248` to `135945781262`,
each with `.attest`, `.msg`, `.sig` and `.tag`, and no `.part` file.

**Power cut while running (powercut log).** Power was removed with the
agent running and no shutdown, then restored. After boot the audit
directory holds no `.part` file (`grep -c part` prints `0`) and every
envelope in it has all four files (the `uniq -c` filter for stems with
other than four files prints nothing). The agent is `active (running)`
and logs its first envelope two seconds after start, counter
`135979335680`, then one every 30 seconds.

## What this does and does not show

It shows that on the reference device, with policy 2.4.3, the agent
publishes envelopes through `.part` and rename, that a failed write leaves
no file under a final name, that `.part` files left by a failed attempt are
removed by the next one, and that after one power cut during operation the
directory held only complete envelopes and the agent resumed on its own.

The power cut was not timed to the write. A cycle is 30 seconds and the
write of one envelope takes a small part of it, so this cut almost
certainly fell between writes. A cut inside the write is covered by the
unit test `interrupted_envelope_is_invisible_and_removed_next_cycle` in
tactiq-attest, not by this record.

The second half of `agent-envelope-not-atomic`, that the audit log does
not show that no envelope is missing, is not addressed. The counter is
consecutive within a boot and starts a new range after each boot
(`…5781262` before the cut, `…9335680` after it), so a gap across a power
cut cannot be read from the directory.

Not covered: the release image (slot B here is a development image), and
the `rauc install` path; slot B was written with `dd`.

## When this stops holding

Run again after a change to the agent's write path (`publish_envelope`,
`remove_partials` in tactiq-attest), to policy module `tactiq_agent` or to
the labelling of `/data/tactiq/audit`, or to the file system type of the
data partition.
