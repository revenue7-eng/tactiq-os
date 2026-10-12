# rc14 release image on the reference device, cold start (2026-10-12)

The release image of v2.1.0-rc14 (build 20261012174949) booted on the
reference Radxa Rock 5A with the rc14 release loader, from a power cycle.
This file records what that boot showed and where each observation can be
checked. It is the measurement behind the rc14 corrections to EX-0004,
EX-0005, EX-0010 and PER-0004/PER-0002 and behind the known issues
tpm-reset-line, rootfs-not-verity and netperm-dev-permission in
`security/coverage-rock5a.v2.1.0-rc14.yaml`.

## What ran

| Item | Value |
|------|-------|
| Build | `20261012174949`, built from tactiq-os `fd1e31d8786c2af2dbb2230a6075a59a4767073f` |
| `idbloader.img` (written at sector 64) | sha256 `431ade7e288a7c983b2e87aff552c069d4a435ed6897a3952f5ced76d10488c8` |
| `u-boot.itb` (written at sector 16384) | sha256 `a2762d4eb2b35eef51bd97edf0d699ee206728fa91f9bf19b6934e19d98c58cb` |
| Slot | B, release image installed by `rauc install` of the build bundle from the development image in slot A |
| Start | power removed and restored (cold start), console on UART ttyS2 |

The loader was written with `dd` from the running development image and read
back before power-off; both read-back hashes equalled the values above. That
read-back is recorded in the session transcript only, not in a separate file.

## Sources

| File | sha256 | What it is |
|------|--------|------------|
| `rel14-coldboot-20261012-uart.log` | `f55e661abd35de0f4b1da527cb78ced29479023d61f926ef4126929ed7336e48` | UART console from power-on to the login prompt, copied from the terminal. The first three lines are the end of the preceding power-off of the development image. |
| `ExportImage.img` (not published) | `30b3bbc5d7e8cc7725d1b1e985f174bb943dcb90e2c6ec416fc4fed508d07e16` | The `data` partition read from the device in maskrom after the run. It holds the systemd journal of the boot, the agent's audit directory and the site network permission. Kept by TactiQ; the extracts below are taken from it. |

The UART log and the journal describe the same boot: both carry the kernel
command line below and the record `audit(2.008:2): enforcing=1`. In the
journal the boot is `70dc754ae174405883eda2ec33bdffe1` (boot 0 of
`/log/journal/2f6341a921d88b7cafaaddb252d7162f`).

## Observations

**Loader (UART log, lines 63, 115, 119 and 135).** SPL of U-Boot 2026.10
prints `SPL measure: TPM reset`, starts the event log and measures `atf-1`,
`atf-2` and `atf-3` into PCR 0, `u-boot` into PCR 4 and `fdt-1` into PCR 6.
U-Boot boots slot B and verifies the kernel and the devicetree of
configuration `conf-rk3588s-rock-5a-b.dtb` with
`sha256,rsa2048:release-fit+ OK`, then prints
`TPM: platform hierarchy disabled`.

**Kernel and keys (UART log).** `Linux version
6.18.52-yocto-standard-00164-g0e7b072c8239`, the version in the name of the
build's `fitImage`. The kernel loads four compiled-in certificates: TactiQ
OS release module signing key, TactiQ Release Root CA, TactiQ Release
Signing CA and TactiQ OS Release IMA Signer. No development certificate is
loaded. `integrity: Unable to open file: /etc/keys/x509_ima.der (-2)` is
expected: the production image ships no IMA certificate (known issue
ima-off-production).

**Root through dm-verity (UART log line 598 and kernel command line;
journal).** The command line creates `rootfs` as a verity target on
`/dev/mmcblk0p4` with 87661 data blocks of 4096 bytes, 701288 sectors,
root hash
`02a7d9becfbd78e297119d9c531dd93e46b5975982efea1a1293254ca57202c9` and salt
`8a7b98d830ac3bf9daa968b9c322bc1e6d9300c632f8f610be59dd67d2c4d797`, the
values in `tactiq-image-tactiq-rock5a.rootfs.ext4.verity-params` of the
build. The kernel reports `dm-0 (rootfs) is ready` and mounts `dm-0`
read-only as root. The refusal of a modified block was not tested in this
run.

**SELinux (UART log line 608; journal).** `audit(2.008:2): enforcing=1
old_enforcing=0`, policy loaded by systemd. The journal of the boot contains
no `avc: denied` record (count 0 over the whole boot, all units).

**Clock.** systemd advanced the clock to the built-in floor,
`2026-10-12 00:00:00 UTC` (the board has no RTC, known issue no-rtc). Journal
timestamps of this boot start from that floor, not from wall time.

**Site network permission (journal, unit tactiq-netperm).** The unit logs
`rejected: signature does not verify; agent stays without network` and
fails; the agent starts. The permission in `/data/site/network-allow` was
left there by development work. Checked on the build host:

- it verifies against `pki/dev/netperm.pem` (`openssl dgst -sha256 -verify`:
  `Verified OK`);
- it does not verify against `/usr/share/tactiq/netperm.pem` read from the
  release rootfs of build 20261012174949 with `debugfs`
  (`Verification failure`); the release build sets
  `TACTIQ_NETPERM_PUBKEY` to the release key.

The refusal is the intended behaviour of a release image. A permission
signed with the release key was not tested.

## Not observed in this run

- PCR values. They were not read; the release values are checked through a
  quote from the agent against the signed RIM after the tag
  (`VERIFY-L3-rc14.md`).
- A warm reboot with the release loader.
- Refusal of a modified root block by dm-verity.
- IMA: the production image has none (known issue ima-off-production).
