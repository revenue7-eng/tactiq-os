# Development image: the rollback floor rises only for an image the slot has booted before (2026-11-09)

This report measures the change to `0010` made after
`rollback-floor-dev-20261108.md`. That report found that the floor rose
on the first boot of any slot that entered with `BOOT_x_LEFT=3`, and a
system that predates the floor installs a slot with 3. The changed `0010`
also requires that U-Boot has booted the same configuration from the same
slot before: it records, per slot, the SHA-256 of the configuration's
signature values in `fit_seen_A` or `fit_seen_B`. The questions of the
earlier report on refusal, on the OS and on a cold start are not repeated
here; its results on raising the floor are replaced by these.

## Questions

1. Does a slot that enters with `BOOT_x_LEFT=3` on the first boot of a new
   image leave the floor where it is?
2. After the OS confirms that slot, does the next boot of the same image
   raise the floor, using the record that U-Boot saved on the boot before?
3. Under the changed loader, is a confirmed slot whose index is below the
   floor refused, with the other slot booted in the same pass?
4. Does the attestation agent of the same image run without denials (the
   agent change of `agent-data-dirs-narrow` and `agent-vault-data-narrow`
   is in this image)?

## Setup

- Board: the Rock 5A reference board. At the start, from the earlier
  report: floor 1; slot B holds an image with rollback index 1, confirmed;
  slot A holds an image with index 0, refused.
- Build: the development tree, tactiq-os `agent-data-dirs-narrow`
  (`41d449e`) and tactiq-os-selinux `agent-vault-data-narrow` (`09f41d6`),
  with the rollback change applied uncommitted, and
  `TACTIQ_ROLLBACK_INDEX = "2"` in the `local.conf` of the development
  tree, for this bench only. The change is committed as `f36a071`.
  `git diff --stat 41d449e f36a071 -- . ':!*.md'` lists, besides the files
  of the change (uncommitted in `41d449e`), the agent change of
  `41d449e` (`tactiq-agent.service`, `tactiq-agent_0.1.1.bb`,
  `data-tactiq-dirs.service`) and the measurement of #306.
- The loader was rebuilt from the files of `f36a071`. The kernel FIT and
  the root file system were built before the last edit of the change,
  which touched only comments in `system.conf` and in the U-Boot files:
  the image carries the earlier comments in `/etc/rauc/system.conf`, with
  the same settings.
- Checked on the host before the board: the root hash in the `/chosen`
  bootargs of both devicetrees in the FIT (`f14fd47e...`) verifies against
  the root file system of the same build with `veritysetup verify`; both
  configurations carry `rollback-index` 2; the FIT inside the boot image
  equals the FIT in deploy (`49722e92...`); `u-boot.itb` contains the new
  message and the extended `CONFIG_ENV_FLAGS_LIST_STATIC`. These were run
  in the session; their output is not in this directory.
- Tools on the board: tpm2-tss 4.1.3; tpm2-tools 5.8 (from the SBOM check
  of this build).
- On the board, in order:
  1. write the loader, read it back, cold start (slot B);
  2. from slot B, write the boot and root file systems of slot A, read
     them back, set `BOOT_A_LEFT=3` and `BOOT_ORDER="A B"` with
     `fw_setenv`, as a system that predates the floor would leave a
     freshly installed slot; cold start;
  3. on slot A: read the environment and the floor, check the agent; then
     reboot after the OS has confirmed A, read the floor;
  4. `BOOT_B_LEFT=3`, `BOOT_ORDER="B A"`, reboot; then
     `BOOT_ORDER="A B"`.

## Files

| file | what |
| --- | --- |
| `step1-loader-b-boot.log` | the loader write and read-back, the first boot of B with this loader, the environment after it |
| `step2-slot-a-write-check.log` | the environment and the read-back of slot A after the write |
| `step3-a-first-boot-and-raise.log` | the first boot of A with the floor read after it, and the next boot of A, which raised the floor, with the floor read after it |
| `step3-a-first-boot-checks.log` | on the first boot of A: the environment, the floor, the agent checks |
| `step4-b-refused.log` | the boot order set to `B A` and the boot in which B is refused |

The three long files are Copy All of the PuTTY window, converted from CRLF
to LF and otherwise unchanged; each begins with the end of the boot
before. The UART adapter dropped during step 2, after the `fw_setenv`
commands and before the power off, and took the PuTTY window with it; the
write and its first read-back were lost with the window. The console was
reopened on the running board, and `step2-slot-a-write-check.log` is the
read-back and the environment taken then. That file and
`step3-a-first-boot-checks.log` were copied from the console into the
chat and saved from there. Sums of every file are in `../SHA256SUMS`.

## Results

| check | result | where |
| --- | --- | --- |
| loader written | read-back `cd6c6984...` and `f7e0a56d...`, equal to the staged sums | `step1-loader-b-boot.log` lines 949 to 952 |
| first boot of B, this loader | `booting slot B (BOOT_B_LEFT now 2, raise 1)`, `Rollback index 1, floor 1 ... OK`, then a second `Saving Environment` | lines 1207 to 1214 |
| record of B | `fit_seen_B=314f6c0d...`, read from the OS | lines 2009 to 2014 |
| slot A written | read-back `ba9e2791...` and `eb0fcec4...`, equal to the files; `BOOT_ORDER=A B`, `BOOT_A_LEFT=3` | `step2-slot-a-write-check.log` |
| first boot of A, entering with 3 | `booting slot A (BOOT_A_LEFT now 2, raise 1)`, `rollback: slot A has not booted this image before, floor not raised`, `Rollback index 2, floor 1 ... OK`, then `Saving Environment` | `step3-a-first-boot-and-raise.log` lines 96 to 104 |
| floor after it | `000 000 000 000 000 000 000 001` | line 911 |
| record of A, A confirmed | `fit_seen_A=efd85a60...`, `BOOT_A_LEFT=3` | `step3-a-first-boot-checks.log` lines 1 to 6 |
| agent | no `tactiq_agent_t` denial in the journal or in `audit.log` after the last `DAEMON_START`; no `read-only`, `denied` or `error` in the agent's journal; service active; envelopes written every 30 seconds to `/data/tactiq/audit`, numbers consecutive | lines 7 to 76 |
| next boot of A | `booting slot A (BOOT_A_LEFT now 2, raise 1)`, `rollback: floor raised to 2`, `Rollback index 2, floor 2 ... OK`; no `has not booted`, no second `Saving Environment` | `step3-a-first-boot-and-raise.log` lines 1238 to 1245 |
| floor after it | `000 000 000 000 000 000 000 003` | line 2039 |
| B, confirmed, index 1 | `booting slot B (BOOT_B_LEFT now 2, raise 1)`, `rollback: index 1 is below floor 2, refused` | `step4-b-refused.log` lines 1232 to 1238 |
| control, same pass | `booting slot A`, `Rollback index 2, floor 2 ... OK`, login on A | lines 1240 to 1246, 2028 |

`agent ... envelopes: 2880 complete` on the login screen did not change
between two logins minutes apart, and showed the same number on other
images and slots. It is not a measure of the agent writing; the journal
and the files are.

## What this establishes

- Question 1: yes. A slot written from the OS and given the counter of a
  confirmed slot did not raise the floor on its first boot, though the
  boot script set `fit_rollback_raise`. The loader of the earlier report
  required only the counter of 3 (its step 4 raised the floor on that
  alone), so by its code it would have raised the floor here; that was not
  run.
- Question 2: yes. After the OS confirmed A, the next boot raised the
  floor to the index of the image, and the record saved on the boot before
  was read back by U-Boot from the saved environment.
- Question 3: yes, against floor 2, with A booted in the same pass. A
  refused configuration is not recorded: after the refusal the only save
  is the boot script's own, before A.
- Question 4: yes, for one boot of about five minutes.

## What this does not establish

- Protection against root, as in `rollback-floor-dev-20261108.md`: root
  writes the loader, and the environment. A forged record in the
  environment can make the floor rise early, which risks a board with no
  slot left to boot, not a rollback.
- That an older release does not boot: the key is the development key.
- The release loader and the release image. Neither was run.
- A slot installed by RAUC. Slot A was written with `dd` and its counter
  set by hand to the value a system that predates the floor leaves.
- The host checks of the setup as raw output in this directory.
- PCRs against the reference of this loader
  (`pcr-ref-seen-20261109.json`): not compared.
- The agent beyond one boot, and its stop path.

## Horizon

A change to `0010` or `0009`, to `fit-rollback.cfg` or the environment
list, to `tactiq-boot-fit.env`, to the rollback index in the kernel FIT,
or a change of TPM, means running the steps again. The floor on this board
is now 2 and cannot be lowered: an image with index 0 or 1 will not boot
on it again.

## Reproduce

On a board with a development loader of this change, floor N, one slot
with an image of index N, confirmed: write an image with index N+1 into
the other slot from the OS, set its counter to 3 and boot it, then boot it
again after the OS confirms it, then set the boot order to the slot with
index N. Expected: the results above, with N+1 in place of 2.
