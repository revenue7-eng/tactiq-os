# First boot on an empty /data: the root of /data is labelled before tactiq-log-setup (2026-11-23)

## Questions

1. Does the root of a new `/data` carry an SELinux label in the image?
2. On the first boot from an empty `/data`, with the change, do
   `tactiq-log-setup` and the audit units that depend on it complete?
3. Is the root relabelled by the new `ExecStartPre`, and from which
   label?
4. Does the boot run without SELinux denials, and do PCR 0 to 9 on the
   board equal the reference of this build?

## Setup

- The change: `ExecStartPre=-/bin/sh -c 'restorecon -v /data'` in
  `recipes-core/tactiq-config/files/tactiq-log-setup.service`, on main
  `64aafb6`. tactiq-os-selinux `ebbcf12`.
- Before the change, on the Rock 5T (2026-10-09):
  `measurements/logs/rock5t-stage1-uart-20261009.log`, lines 669 to 678,
  `mkdir: can't create directory '/data/': Permission denied` and
  `tactiq-log-setup: completed with errors` on the first boot only. On the
  Rock 5A the same failure, with `Load TactiQ audit rules for the data
  partition` also failed, was seen on 2026-11-21 on the first boot of the
  development `.wic` `20261118105152`. That console is not in this
  repository; this report does not rest on it.
- Question 1 was checked on the release `.wic` of 2026-11-20
  (`tactiq-image-tactiq-rock5a.rootfs-20261120073756.wic`) on the build
  host, without the board. The data partition starts at sector 9461760
  (`sfdisk -d`, `name="data"`):

  ```
  $ debugfs -R 'stats' "<wic>?offset=$((9461760*512))" | head -n 2
  Filesystem volume name:   data
  $ debugfs -R 'ls -l /' "<wic>?offset=$((9461760*512))"
        2   40755 (2)      0      0    4096  6-Apr-2011 03:00 .
        2   40755 (2)      0      0    4096  6-Apr-2011 03:00 ..
       11   40700 (2)      0      0   16384  6-Apr-2011 03:00 lost+found
  $ debugfs -R 'ea_list /' "<wic>?offset=$((9461760*512))"
  (no output)
  ```

  The same `ea_list` on `/usr/sbin/tactiq-log-setup` in the release root
  file system prints `security.selinux (44)`, so the empty output above is
  an absent attribute, not a command that prints nothing.
- Built in the development tree from branch
  `fix/data-root-label-first-boot` (main `64aafb6` with this change,
  uncommitted at build time). `bitbake tactiq-image-dev`, then
  `bitbake -c cleansstate tactiq-slot-dtb linux-yocto-fitimage
  tactiq-boot-image` and `bitbake tactiq-image-dev` again, so that the FIT
  carries the root hash of this root file system. Image stamp
  `20261123132120`; root hash
  `0b51eb905a8b334ae720c200f248c900c06eda122cd3e802a5a7c242a4931839`;
  `.wic` sha256
  `d6d76f93e4c4383641559d8a5c1b3a5536d08305f54ad2016ac4c86e566c5840`.
  `debugfs -R 'cat /usr/lib/systemd/system/tactiq-log-setup.service'` on
  the built root file system shows the new `ExecStartPre` line.
- Board: the Rock 5A reference board `TACTIQ-BENCH-001`, rollback floor 2.
  `/data` was saved before the write. The full `.wic` was written to the
  eMMC, replacing the loader, both slots and `/data`. First boot from
  slot A on the empty `/data`, then the agent identity was restored as in
  the board runbook, then a cold start (power pulled) and a second boot.

## Files

| file | what |
| --- | --- |
| `board-session-a.log` | the serial console of the session, saved from the terminal's clipboard: the first boot from U-Boot on (the DDR and SPL lines of that boot were already out of the terminal's scrollback), the checks, the restore of the agent identity, the power-off, the second boot from DDR init, and `tpm2_pcrread` |
| `pcr-ref-datafix-20261123.json` | the reference of this build, from `mk-pcr-reference.py` |

Sums of both files are in `../SHA256SUMS`. Line numbers below are lines
of `board-session-a.log`.

## Results

| question | result |
| --- | --- |
| 1 | no. The root of the data partition in the release `.wic` has no extended attributes, so on the board it reads as `unlabeled_t`. `tactiq_log.te` grants `tactiq_logsetup_t` nothing on `unlabeled_t` |
| 2 | yes. First boot: `Finished TactiQ Level 0 logging` (716), `Mounted Persistent audit log` and `Mounted Persistent journal on the TactiQ data partition` (730, 731), `Started Security Audit Logging Service` (737), `Finished Load TactiQ audit rules for the data partition` (774). The file has no `tactiq-log-setup: FAILED` and no `Permission denied` line. The second boot shows the same units completing (1927, 1985) |
| 3 | yes. `journalctl -b -u tactiq-log-setup` (835): `sh[263]: Relabeled /data from system_u:object_r:unlabeled_t:s0 to system_u:object_r:tactiq_vault_data_t:s0`, between the start and the finish of the unit. `ls -laZ /data` (815 to 821) shows `tactiq_vault_data_t` on `/data` and `/data/log` |
| 4 | yes. 0 lines `avc:.*denied` in the journal of the first boot (837, 838). After the cold start, `tpm2_pcrread` (2025 to 2037): PCR 0 to 9 equal the slot A values under `pcr` in `pcr-ref-datafix-20261123.json`. PCR 10 is not in the reference |

## What this shows and what it does not

- The relabel runs through the `sh` of the unit, the same path the
  relabel in `data-tactiq-dirs` takes; this run shows that it succeeds
  there. Which domain it ran in was not read on the board.
- On the first boot `tactiq-agent` fails (791) and `tactiq-stop` exits
  (935 and the lines after it): both read `/data/tactiq/keys/device_id`,
  which an empty `/data` does not have. Both start once the identity is
  restored (915, 968). This is unrelated to the change.
- At the power-off, `Failed unmounting Persistent journal on the TactiQ
  data partition` (1007) and `Failed unmounting /var/volatile` (1101).
  The same two lines were recorded on the Rock 5T on 2026-10-09. Not
  investigated here.
- `systemd-networkd-wait-online` fails on this board, which has no
  network (824). Not investigated here.
- On the Rock 5T before the change the persistent journal was still
  mounted on the failing boot. Whether a first boot without the change
  loses its journal was not measured; the change is shown to fix the
  creation and relabel of `/data/log` and the audit units, not to recover
  a lost journal.
- One board, one first boot, the development image. The release image
  with this change was not built or booted.
