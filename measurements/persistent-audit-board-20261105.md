# Development image: an audit record that survives a cold start, and a boot without SELinux denials (2026-11-05)

## Questions

1. Does a record written by auditd survive a cold start of the board?
2. Is it the rule that makes the record: with the rule removed, does the
   same kind of event leave none?
3. Does a boot with auditd running leave no SELinux denial, counted so that
   records of earlier boots, kept in the same persistent log, are not
   counted?
4. Was the board running the build these changes were measured on?

## Setup

- Board: the Rock 5A reference board, slot A, cold start (power pulled,
  then on). The board's `/etc/tactiq-release` is at the top of the session
  in `board-session-1.log`: `tactiq-image-dev`, `v2.1.0-rc14`.
- Build: the development image from tactiq-os `552e5fc` and
  tactiq-os-selinux `ed5f1b8`, the branch commits of #301 and #37. The
  merged commits differ from them only as follows:
  `git diff --stat 552e5fc 5a2ced3` in tactiq-os lists
  `integration/LAYERS.lock` and `recipes-core/images/tactiq-image.bb`
  (the pin of the policy and a comment); `git diff --stat ed5f1b8 1c09d78`
  in tactiq-os-selinux is empty.
- Reference: `pcr-ref-audit2-20261105.json`, made with
  `mk-pcr-reference.py` from `fitImage`, `u-boot.itb` and `idbloader.img`
  of that build.
- On the board (console in `board-session-1.log` and
  `board-session-2.log`):
  1. state: slot, auditd and the unit that loads the rules for `/data`,
     the loaded rules, the bind of `/data/log/audit`, its label, the count
     of denials in the journal, the order of `DAEMON_START` and `AVC` lines
     in `audit.log`, `tpm2_pcrread`;
  2. `touch /data/site/audit-probe-5`, then `ausearch -k site-config`;
  3. `poweroff`, power pulled, power on;
  4. `ausearch -k site-config` for `audit-probe-5` again, the count of
     denials in the journal;
  5. `auditctl -d` of the rule on `/data/site`, `touch
     /data/site/audit-probe-6`, `ausearch -k site-config` for it.

## Files

| file | what |
| --- | --- |
| `board-session-1.log` | the console from power on to step 2 |
| `board-session-2.log` | the console from power on to step 5, the same window; its first five lines scrolled out of PuTTY, `board-session-1.log` has them |
| `pcr-ref-audit2-20261105.json` | the reference of the build |
| `pcr-match.log` | `~/bin/pcr-match` run on `board-session-1.log` |

The console was copied from PuTTY through Notepad, which wrote CRLF line
endings; they were converted to LF before the sums were taken, and nothing
else was changed. Sums of every file are in `../SHA256SUMS`.

## Results

| check | result | where |
| --- | --- | --- |
| slot, image | A, `tactiq-image-dev` v2.1.0-rc14 | `board-session-1.log` lines 919 to 926 |
| auditd, rules for `/data` | both `active`; five rules, all in syscall form, none `-w` | lines 927 to 935 |
| log on `/data` | `/dev/mmcblk0p5[/log/audit]` on `/var/volatile/log/audit`; directory `0700`, `auditd_log_t` | lines 936 to 942 |
| denials, journal | `0` | line 944 |
| denials, `audit.log` | five `DAEMON_START` lines (1, 155, 285, 439, 590), one per start of auditd; one `AVC` after each of the first three (65, 218, 348), none after the fourth or the fifth, which is this boot | lines 945 to 953 |
| PCR 0 to 9 | equal to the slot A entries of the reference | `pcr-match.log` |
| `audit-probe-5` recorded | yes, `2` lines (directory and file) | line 969 |
| after the cold start: `audit-probe-5` | found, `2` lines; nothing touched it after the start | `board-session-2.log` line 2021 |
| after the cold start: denials, journal | `0` | line 2023 |
| rule removed: `site-config` rules | `0` | line 2026 |
| rule removed: `audit-probe-6` recorded | no, `0` | line 2029 |

The three earlier denials are `auditctl_t` writing to `/dev/log`, from the
boots of the build before `552e5fc`, whose rules were in `-w` form. They
stay in `audit.log` because it persists; they are not of this build.

The board has no clock: every boot starts at the same time (2026-10-12
00:00), so the times in `audit.log` and `ausearch -ts boot` cannot tell
boots apart. That is why denials are counted in the journal, which tells
boots apart by their id, and in `audit.log` by position after the last
`DAEMON_START`, not by time.

## What this establishes

- Question 1: yes. The record of `audit-probe-5` was written before the
  cold start and found after it, with no event in between.
- Question 2: yes, for the rule on `/data/site`: with it removed, a touch
  of `audit-probe-6` left no record, while with it a touch of
  `audit-probe-5` did.
- Question 3: yes, for both boots of this run.
- Question 4: yes, PCR 0 to 9 equal the reference of the build.

## What this does not establish

- Anything about the release image. It installs auditd too (#301), but it
  was not run.
- That the times of the records mean anything. Order within `audit.log`
  holds; times do not (see above).
- That the log cannot be changed. root can edit or remove `audit.log`; it
  is not signed and not anchored in the TPM.
- Rotation and the bound on space (5 files of 8 MB), which were not
  reached.
- The other rules (modules, clock, `rauc`, `/data/tactiq/stop`). They were
  loaded, as `auditctl -l` shows, but no event of theirs was made.
- Events that need no rule: logins through PAM and SELinux denials are
  recorded by libaudit and the kernel, which this run did not exercise
  beyond the denial count.

## Horizon

The record holds for the build it names. A change to
`recipes-security/audit`, to the log units of `tactiq-config`
(`tactiq-log-setup`, `var-volatile-log-audit.mount`) or to `tactiq_log`
in tactiq-os-selinux means running the steps again.

## Reproduce

On a board with a development image from tactiq-os `5a2ced3` or later,
after a cold start, the commands of the setup in that order. Expected: the
results above, with the line numbers of that session.
