# Development image: U-Boot refuses a signed FIT below a rollback floor kept in TPM NV (2026-11-08)

## Questions

1. Does U-Boot refuse a correctly signed FIT whose rollback index is
   below the floor, and boot the other slot in the same pass?
2. Can the operating system, as root, raise, clear or remove the floor?
3. Is the floor raised only for a slot the operating system has marked
   good, and not for a slot that has just been written?
4. Does the floor survive a cold start, in which SPL resets the TPM
   (#224)?

## Setup

- Board: the Rock 5A reference board, boot medium eMMC. Two slots:
  A holds the development image of #301 (rollback index 0, root hash
  `2142ed2a...` in its kernel command line); B holds a development image
  of this change (rollback index 1, root hash `2015b837...`).
- Build: the development image and loader built in the development tree
  from tactiq-os `4214fed` with an earlier version of the change applied
  uncommitted. That version is not in any commit. It differs from
  `f36a071`, where the change is committed, in `0010` (sha256 of the
  earlier patch `53c53b03c36ddf96b96529bdb7e1ac53ce53e7832d4ee163fa9c67e061420001`),
  in `fit-rollback.cfg`, the environment list check of the U-Boot recipe
  and comments, all from the change measured in
  `rollback-seen-dev-20261109.md`; the comparison with the floor and the
  refusal are the same in both versions. The tree of `f36a071` also has
  the commits merged to main after `4214fed`.
- Floor: TPM NV index `0x01500018`, type bits, defined by U-Boot under
  the platform hierarchy, written only with platform authorization
  (`ppwrite`); the platform hierarchy is locked before the OS starts.
  The floor N is the N low bits set.
- Tools on the board: tpm2-tss 4.1.3 (from the paths in the error
  lines of `step2-os-refusals.log`). tpm2-tools 5.8, the version in the
  SBOM check of a build of the same tree on 2026-11-09; the build of this
  report was not checked for it.
- On the board, in order (console in the files below):
  1. write the loader (`idbloader.img` at sector 64, `u-boot.itb` at
     sector 16384), read it back, cold start;
  2. from the OS, try to set bits of the floor under the platform, the
     owner and the index itself, to undefine it under the platform and
     the owner, and to read it;
  3. write the root file system of slot B, set `BOOT_B_LEFT=2` and
     `BOOT_ORDER="B A"` with `fw_setenv`, reboot;
  4. after the OS marked B good, reboot;
  5. `fw_setenv BOOT_ORDER "A B"`, reboot;
  6. `poweroff`, power pulled, power on; read the floor and its
     attributes from the OS; `fw_setenv BOOT_ORDER "B A"`.

## Files

| file | what |
| --- | --- |
| `step1-loader.log` | boot with the previous loader, its write and read-back, the first boot with this loader |
| `step2-os-refusals.log` | the six attempts of the OS on the floor, with its public area before and after |
| `step3-b-verity-fail.log` | the first try of slot B, refused by dm-verity, and the fall back to A |
| `step3-b-boot.log` | the write of the root file system of slot B and the first boot of B |
| `step4-floor-raised.log` | the slot B counters after the OS marked it good, and the boot that raised the floor |
| `step5-a-refused.log` | the boot order set to `A B` and the boot in which A is refused |
| `step6-coldboot.log` | the cold start, the refusal again, the floor read from the OS |

Each file is one Copy All of the PuTTY window, so most of them begin
with the end of the boot before (for example the first boot of
`step6-coldboot.log` is the boot of `step5-a-refused.log`). The windows
were copied as they were; nothing was removed. Sums of every file are
in `../SHA256SUMS`.

## Results

| check | result | where |
| --- | --- | --- |
| loader written | read-back `fdbe2f7d...` and `2714870e...`, equal to the staged sums | `step1-loader.log` lines 919 to 933 |
| first boot of this loader | `booting slot A (BOOT_A_LEFT now 2, raise 1)`, `rollback: floor index defined`, `Rollback index 0, floor 0 ... OK` | `step1-loader.log` lines 1189 to 1195 |
| floor from the OS, before | attributes `0x40050021`, not written | `step2-os-refusals.log` lines 16 to 25 |
| set bits: platform, owner, index | `0x185`, `0x149`, `0x12F` | lines 27 to 41 |
| undefine: platform, owner | `0x185`, `0x149` | lines 42 to 53 |
| read under the index | `0x14A`, not initialized | lines 54 to 59 |
| floor from the OS, after | attributes `0x40050021`, unchanged | lines 60 to 69 |
| slot B, unconfirmed, broken root file system | `booting slot B (BOOT_B_LEFT now 0, raise 0)`, `Rollback index 1, floor 0 ... OK`, then `metadata block 111039 is corrupted`, panic; next boot A, floor 0 | `step3-b-verity-fail.log` lines 430, 592 to 597, 1080, 1242 to 1247 |
| slot B, unconfirmed | `BOOT_B_LEFT=2` set; `booting slot B (BOOT_B_LEFT now 1, raise 0)`, `Rollback index 1, floor 0 ... OK`, login on B | `step3-b-boot.log` lines 924 to 929, 1185 to 1190, 1987 |
| slot B marked good by the OS | `BOOT_B_LEFT=3` | `step4-floor-raised.log` lines 956 to 959 |
| floor raised | `booting slot B (BOOT_B_LEFT now 2, raise 1)`, `rollback: floor raised to 1`, `Rollback index 1, floor 1 ... OK` | lines 1234 to 1240 |
| boot order `A B` | `BOOT_ORDER=A B`, `BOOT_A_LEFT=3` | `step5-a-refused.log` lines 971 to 975 |
| slot A refused | `booting slot A (BOOT_A_LEFT now 2, raise 1)`, `rollback: index 0 is below floor 1, refused` | lines 1230 to 1235 |
| control, same pass | `booting slot B`, `Rollback index 1, floor 1 ... OK`, login on B | lines 1238 to 1243, 2030 |
| cold start | `SPL measure: TPM reset`; `booting slot A (BOOT_A_LEFT now 1, raise 0)`, `index 0 is below floor 1, refused`; B, `floor 1 ... OK` | `step6-coldboot.log` lines 1168, 1220 to 1233 |
| floor from the OS, after the cold start | `000 000 000 000 000 000 000 001`; attributes `0x60050021`, written | lines 2025 to 2036 |

After a refusal U-Boot also prints `ERROR -2: No such file or directory:
can't get kernel image!` (`step5-a-refused.log` line 1236). That is the
generic message of `bootm`; the cause is the line above it.

tpm2-tools prints the type as `nt=0x1` for this index of type bits
(`step2-os-refusals.log` line 23). The raw attribute value is correct;
the printed field is not.

## What this establishes

- Question 1: yes. A signed FIT with index 0 was refused against floor
  1, twice (after a reboot and after a cold start), and in the same pass
  U-Boot booted slot B, whose index 1 met the floor. Setting the boot
  order from the OS, which before this change booted the older slot, no
  longer does; see below for what root can still do.
- Question 2: yes, for the six operations tried. Each was refused, and
  the public area of the index was the same before and after.
- Question 3: yes, for the two unconfirmed boots of B: neither raised the
  floor (`raise 0`, floor 0), including the one whose root file system
  dm-verity refused. The floor was raised on the first boot of B after
  the OS marked it good.
- Question 4: yes. After a cold start in which SPL reset the TPM, the
  floor was 1, U-Boot refused A again, and the OS read the floor as 1
  with the `written` attribute set.

## What this does not establish

- Protection against root on this board. Step 1 wrote the loader from
  the OS, as root, with SELinux enforcing (`step1-loader.log` lines 923
  to 928). root can equally write a loader without the floor check, and
  then any older signed FIT boots. The floor holds against an older
  signed image installed through the update channel, or written by a
  process that can write the slots and the environment but not the
  loader area. Against root it holds only once the loader itself is
  authenticated by the boot ROM and cannot be rolled back
  (`THREAT_MODEL.md`, the OTP key).
- That an older release does not boot. The image is signed with the
  development key, which is public, so anyone can sign an image with any
  index. That property means something only under the release key, and
  is measured on the release build.
- The release loader and the release image. Neither was run.
- That the board ran exactly the build named above: the loader read-back
  equals the staged files, and the root hashes in the kernel command
  lines are those of the two images, but no PCR reference of slot B was
  made and PCRs were not compared.
- The failure before this change (the older slot booted after a change
  of `BOOT_ORDER` from the OS). It was observed in a session of
  2026-11-05 whose console is not in this directory.
- The write of the FIT of slot B, and the expected value of the read-back
  of its root file system (`step3-b-boot.log` line 923 prints the sum;
  no line states what it should be). The first boot of the first try of
  slot B scrolled out of the window; only the second is in
  `step3-b-verity-fail.log`.
- A slot installed by a system without `boot-attempts-primary=2`. The
  distinction between a confirmed slot (3) and a freshly installed one
  (2) depends on it; slot B here was set to 2 by hand. A slot installed
  with 3 raised the floor on its first boot under this loader's code; the
  change that closes this is measured in `rollback-seen-dev-20261109.md`.

## Horizon

The record holds for the build it names. A change to the U-Boot patches
`0009` and `0010`, to `fit-rollback.cfg`, to `tactiq-boot-fit.env`, to
`boot-attempts-primary` in `system.conf`, to the rollback index in the
kernel FIT, or a change of TPM, means running the steps again. The floor
on this board is now 1 and cannot be lowered: an image with index 0 will
not boot on it again.

## Reproduce

On a board with a development loader and image of this change, a slot
with index 0 and a slot with index 1, the floor index not yet defined:
the steps of the setup in that order. Expected: the results above.
Steps 3 and 4 raise the floor for good.
