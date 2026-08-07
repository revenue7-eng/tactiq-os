# RAUC Bundle Hooks under SELinux Confinement — 2026-08-06

**DRAFT — author to review wording before commit.**

RAUC upstream (Jan Lübbe, Pengutronix) proposed adding a `bundle-mount-context`
option to `system.conf` and asked which SELinux context the mounted bundle
should carry. Bundle hooks execute directly from the bundle mount point
(`run_bundle_hook()`, `src/install.c:887`, spawned from `bundle->mount_point`),
so that context decides whether hooks run at all. This test establishes what
the current policy does and what is required to make hooks work.

## Summary

A RAUC bundle hook cannot execute under the current policy: the denial is
`{ execute }` on the bundle-mount type `tactiq_squashfs_t`.

Granting execute on the bundle content is **not sufficient** for a script hook.
The interpreter named in the shebang lives in the rootfs under its own type
(`shell_exec_t` here) and needs a separate rule. Once both rules are present
the hook runs end to end.

For the `bundle-mount-context` proposal this means the option alone does not
make hooks work. Whatever default is chosen, integrators shipping script hooks
need a second rule that has nothing to do with the mount context — it concerns
the rootfs. The first denial is discoverable from an AVC log; the second only
appears once the first is fixed.

The same gap exists in the merged upstream refpolicy module
(`SELinuxProject/refpolicy`, module commit `9417c19`, merge `5852e53`), which
grants no execute permission on bundle content either.

Two limits on the above. A compiled binary hook was **not** tested; the claim
that it would need only the first rule follows from the exec mechanism, not
from measurement. And the absence of further denials is established only up to
the point where the hook rejected the bundle — the rest of the install path was
never exercised, by design.

## Test system

| Item | Value |
|---|---|
| Board | Rock 5A (RK3588S), air-gapped, serial console only |
| Image | `tactiq-image-dev-tactiq-rock5a.rootfs-20260806073130` |
| SELinux | `targeted`, enforcing, policy version 35, MLS enabled |
| Loaded RAUC module | `tactiq_rauc` (product module, not upstream refpolicy `rauc`) |
| `TACTIQ_META_TACTIQ_GIT` | `d99725b6e7671168edf41fc29cf6c5987b08c0fc` |

Squashfs labelling comes from `0001-squashfs-genfscon-tactiq.patch`, which
replaces `fs_use_xattr squashfs` with
`genfscon squashfs / -> tactiq_squashfs_t`.

The image was built in `~/build-rock5a-spike` against the `/mnt/d/tactiq-os`
clone. That build directory was later repointed at a different clone, so
rebuilding this image requires the SELinux tooling subpackages added by this
commit to be present in whichever tree `bblayers.conf` names at the time.

The board clock was set manually before each run: there is no usable RTC and no
NTP on an air-gapped node, and the signing certificate's `Not Before` is
2026-07-14.

## Test bundle

Minimal verity bundle, no images, one `install-check` hook.

```
[update]
compatible=TactiQ OS Rock5A
version=hooktest

[bundle]
format=verity

[hooks]
filename=hook
hooks=install-check
```

```sh
#!/bin/sh
echo "HOOK RAN: $1" >&2
exit 10
```

Exit code >= 10 rejects the bundle, so the run stops before any slot write
whether or not the hook executes. `install-check` runs immediately after mount
and replaces the compatible check (`src/install.c:1617`), so the bundle needs
no matching images. A padding file was required because `rauc bundle` rejects a
squashfs of exactly 4096 bytes.

Built on the host with `rauc-native` 1.15.2 (same version as target), signed
with the published `pki/dev` chain.

| Artifact | Value |
|---|---|
| Bundle sha256 | `2238bcf3a59dc01c10ec733ce990c81e5c5fde69904e7ffef59aa3c7f912c164` |
| Size | 32 433 bytes |
| Label on device | `system_u:object_r:tactiq_rauc_bundle_t:s0` |

The keyring on the device was pointed at the `pki/dev` root CA
(`path=/etc/rauc/dev-ca.pem`, `check-purpose=codesign`), with the original
preserved as `system.conf.orig`.

That configuration was assembled by hand on the card, before `47511c1` (#78)
landed on the same day. It is equivalent to what the product now ships by
default: the same root of trust, the same `check-purpose`, the same
intermediate in the signature. The only difference is the filename — the
product installs the root CA as `/etc/rauc/root-ca.pem`. The measurement
therefore reflects the current default configuration, not a special case.

## Run 1 — baseline

`selinux-rauc-hook-exec-run1-20260806.log`

Policy before the run:

```
allow tactiq_rauc_t tactiq_squashfs_t:file { getattr ioctl lock open read };
```

`execute` absent. `rauc install` fails at 40%, before slot writes:

```
LastError: Install-check hook failed: failed to start bundle hook:
Failed to execute child process "/run/rauc/mnt/bundle/hook" (Permission denied)
```

```
audit[445]: AVC avc: denied { execute } for pid=445 comm="installer"
name="hook" dev="dm-0" ino=1
scontext=system_u:system_r:tactiq_rauc_t:s0
tcontext=system_u:object_r:tactiq_squashfs_t:s0 tclass=file permissive=0
```

`dev="dm-0"` is the device-mapper verity device backing the bundle mount, so
the denial is on execution from the mount point itself. This matches
`tactiq_rauc.te:123` and was predicted from the policy source before the run.

## Run 2 — execute on bundle content

`selinux-rauc-hook-exec-run2-20260806.log`

Rule added as a CIL module:

```
(allow tactiq_rauc_t tactiq_squashfs_t (file (execute execute_no_trans)))
```

`semodule -i` returns 1 because `load_policy` is absent from the image (see
Method notes), but it does write the rebuilt policy. Loaded into the kernel
directly:

```
allow tactiq_rauc_t tactiq_squashfs_t:file
    { execute execute_no_trans getattr ioctl lock open read };
```

`rauc install` still fails at 40% with the same RAUC-level message, but the
denial has moved:

```
audit[719]: AVC avc: denied { execute } for pid=719 comm="installer"
name="bash.bash" dev="mmcblk1p2" ino=611
scontext=system_u:system_r:tactiq_rauc_t:s0
tcontext=system_u:object_r:shell_exec_t:s0 tclass=file permissive=0
```

The hook begins with `#!/bin/sh`, so the kernel executes the interpreter, not
the hook file. `bash.bash` is `shell_exec_t` and lives on `mmcblk1p2` — the
rootfs, not the bundle. The bundle-mount context does not cover it.

## Run 3 — execute on bundle content and on the interpreter

`selinux-rauc-hook-exec-run3-20260806.log`

Installing the `shell_exec_t` rule as a second, separate module produced a
policy containing only that rule; the `tactiq_squashfs_t` rule from run 2 was
no longer present, and the install failed again on `tactiq_squashfs_t`
(17:50:39). Both rules were then supplied in one CIL file:

```
(allow tactiq_rauc_t tactiq_squashfs_t (file (execute execute_no_trans)))
(allow tactiq_rauc_t shell_exec_t (file (execute execute_no_trans open read getattr ioctl map)))
```

Kernel policy after loading:

```
allow tactiq_rauc_t tactiq_squashfs_t:file { execute execute_no_trans getattr ioctl lock open read };
allow tactiq_rauc_t shell_exec_t:file    { execute execute_no_trans getattr ioctl map open read };
```

Result:

```
LastError: Bundle rejected: Hook returned: 'HOOK RAN: install-check'
```

That string is the hook's own `echo`, and the rejection is its `exit 10`. The
hook executed end to end. No new denial from `tactiq_rauc_t` appears after this
install — the only such entry in the window is the 17:50:39 one from the
earlier attempt. Slots untouched: `rootfs.0` booted, both slots `good`.

## Method notes

Each of these cost time to establish and none is documented in an obvious
place.

**`rauc bundle --intermediate`.** `--cert` uses only the first certificate as
the signer; intermediates must be passed separately
(`src/signature.c:580-589`). A concatenated chain in `--cert` silently drops
the intermediate and verification fails with
`unable to get local issuer certificate`.

**`check-purpose`.** Without it OpenSSL defaults to `smimesign`
(`docs/reference.rst:370`). The `pki/dev` signer carries
`extendedKeyUsage = codeSigning`, so verification fails with
`unsuitable certificate purpose` until `check-purpose=codesign` is set.

Both of the above were hit here while building the test bundle by hand, and
independently the same day while unifying the signing PKI (`47511c1`, #78).
They are now the shipped defaults — `BUNDLE_ARGS += "--intermediate=..."` in
`recipes-core/bundles/tactiq-bundle.bb` and `check-purpose=codesign` in
`recipes-core/rauc/files/system.conf` — so neither is a manual step any more.
Recorded because both fail with an error message that does not name the cause.

**Target RAUC has no `bundle` command** — only `extract`, `info`, `service`,
`install`, `status`, `mount`, `write-slot`. Bundles are built on the host.

**`genfscon` cannot ship in a loadable module.** In `checkpolicy`'s grammar
`opt_genfs_contexts` appears only in `base_policy`
(`checkpolicy/policy_parse.y:178`). The squashfs type is fixed at image build
time.

**Loading policy without `load_policy`.** `cat > /sys/fs/selinux/load` fails
with `Invalid argument` — the kernel expects the policy in a single write.
`dd bs=2M` works.

**Missing subpackages.** `policycoreutils` and `libselinux` are split; the
image initially lacked `policycoreutils-hll`, `libselinux-bin` and
`policycoreutils-loadpolicy`. The first two were added to
`tactiq-image-dev.bb`; the third was worked around with `dd`.

## Observations outside this test

Recorded for separate triage; none was investigated here.

**No time source on the device.** The Rock 5A has no usable RTC, and an
air-gapped node has no NTP. systemd sets the clock to the build epoch — here
2026-03-13 — which is earlier than the signer's `Not Before`, so a valid
bundle is rejected with `certificate is not yet valid`. `date -s` was issued
manually before each run in this test, but that is a bench workaround: **a node
with no time source cannot take an update at all.** Encountered independently
the same day during the PKI unification work. `--no-check-time` would bypass
the check rather than solve it; the options are an RTC on the board, a time
sync before install, or an explicit prerequisite in the procedure.

**`semodule` is not usable on this policy.** Run 3's log contains 1766 AVC
denials with `scontext=...semanage_t`, mostly `relabelfrom` on
`semanage_store_t` and `file_context_t`, against 2 from `tactiq_rauc_t` and 2
from `udev_t`. Every `semodule` invocation produces this flood. It is also the
likely reason the run-2 rule did not survive into the run-3 policy — the store
update could not complete consistently — though that causal link is inferred,
not measured.

**`udev_t` denials on bundle files.** `getattr` on the bundle, twice per
install. `tactiq_rauc.te` already carries
`dontaudit udev_t tactiq_vault_data_t:file getattr` for the `/data` path; there
is no equivalent for `tactiq_rauc_bundle_t`.

**Boot-time failures**, both visible on every boot of this image:
`Failed to start SELinux autorelabel service loading` and
`systemd-fstab-generator: Failed to parse '/etc/fstab': Permission denied`.

**`/var/lib/tactiq` top level** has no `file_contexts` entry, only its
per-service subdirectories, so `restorecon` resolves it to `var_lib_t`.

**Capture discipline.** Neither the July 2026 enforcing runs nor the first
attempt at this one recorded image identity, `sestatus` or `semodule -l` at the
head of the capture; the July logs consequently cannot establish which policy
variant was loaded. The state-fixation block used here should open every future
capture, and captures should be written to a file on the device rather than
read off the console.

## Evidence

Logs were written on the device to `/data/measurements/` and retrieved by
mounting the card on the build host. Hashes were computed on the device and
re-verified after transfer; all three match and are recorded in
`measurements/SHA256SUMS`.

| File | Bytes | sha256 |
|---|---|---|
| `selinux-rauc-hook-exec-run1-20260806.log` | 2 730 | `7b3d3cb438bac118191834fbd908ca3045aae04c4e7535e6be56f4cab91c38f1` |
| `selinux-rauc-hook-exec-run2-20260806.log` | 3 152 | `532f9b8b97b98a7adf6c199c55a240a585388d23ce1912e32582fb0ef76ffc6f` |
| `selinux-rauc-hook-exec-run3-20260806.log` | 498 925 | `95a61c0488e41614750b194fb42d4447e8f185b48aec9347b162d4abc99bc410` |

The logs are unedited, including the `semanage_t` denial flood in run 3. Run 2's
log opens with two `=== run 2` headers because the setup block was executed
twice; the second attempt is the one that proceeded.
