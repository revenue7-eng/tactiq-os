# Development image: IMA appraisal requires a signature, and tmpfs and ramfs no longer exempt execution (2026-11-09)

## Questions

1. Does the development image enforce IMA appraisal, as its command line
   carries no `ima_appraise=`?
2. Before this change, does a sha256 digest in `security.ima`, written by
   root, make an unsigned file on `/data` readable?
3. With `appraise_type=imasig` on every appraise rule, is such a digest
   refused, while a file signed under the development IMA key is read?
4. With the tmpfs and ramfs exemptions narrowed to `func=FILE_CHECK`, is an
   unsigned program refused when run from `/tmp` and from a ramfs root
   mounts?
5. Does the image boot and run without IMA or SELinux refusals of its own?

## Setup

- Board: the Rock 5A reference board `TACTIQ-BENCH-001`, rollback floor 2.
- Before (`before-old-image.log`): the image then in slot B,
  `tactiq-image-dev` `v2.1.0-rc14`, built before this change; its policy
  has no `appraise_type=imasig` and exempts tmpfs and ramfs whole.
- After: `tactiq-image-dev` built in the development tree from
  `fix/ima-imasig` (main `ae814cd` with this change applied) and
  tactiq-os-selinux `main` `6c93b25`, the revision `integration/LAYERS.lock`
  pins. Image stamp `20261109060632`; the boot file system sha256
  `e1069d94c8564bf60ea9d6c66e253529532aa2be35526cf916e71cfc296ad3e5`, the
  root file system (`.ext4.verity`, 458403840 bytes)
  `eff5c089ffd5000254a479f474e400fe02704d790300e8ee43a51c6a338f4f26`.
  The policy in the root file system was read from the artifact with
  `debugfs` before delivery: three appraise rules with
  `appraise_type=imasig`, and `func=FILE_CHECK` on the tmpfs and ramfs
  exemptions.
- Delivery: from slot A, both partitions of slot B written with `dd` and
  read back to the sums above; `rauc status mark-active other`; cold start
  (power pulled). U-Boot: `booting slot B`, `Rollback index 2, floor 2 ...
  OK` (`write-and-boot-b.log`, which also holds the boot of slot A before
  the write).
- Probe files placed on `/data` from slot A before the switch:
  `signed.txt`, signed with `pki/dev/ima-signer.key.pem` on the PC
  (`evmctl ima_sign --sigfile`) and given that signature with
  `evmctl ima_setxattr --sigfile`; `probe.txt`, given the digest
  `0x0404` + sha256 of its content with `setfattr`.

## Files

| file | what |
| --- | --- |
| `before-old-image.log` | the image before the change: release identity, board state, the digest probe, the measurement list entry, the mounts, and the survey of `security.ima` on the root file system and `/data` |
| `write-and-boot-b.log` | the console from the boot of slot A through the write of slot B, the switch and the boot of slot B |
| `checks-b.log` | the checks on slot B |
| `pcr-b.log` | PCR 0 to 10 read on slot B after the cold start |
| `pcr-ref-imasig-20261109.json` | the reference of this build, from `mk-pcr-reference.py` |

Sums of every file are in `../SHA256SUMS`.

## Results

| question | result |
| --- | --- |
| 1 | the board state block reads `cmdline=none`; an unsigned file on `/data` is refused to root (`cause=missing-hash`). The kernel default without the argument is enforce (`ima_appraise = IMA_APPRAISE_ENFORCE` in `ima_main.c`; `CONFIG_IMA_APPRAISE_BOOTPARAM=y`) |
| 2 | yes: after `setfattr` of the digest, `cat` printed the file; the read was measured into PCR 11 as an `ima-sig` entry without a signature |
| 3 | the digest probe refused, `cause=IMA-signature-required`; `signed.txt` read |
| 4 | `/tmp/bb` (a copy of `/bin/busybox`, without its xattr) refused, `cause=IMA-signature-required`, `dev="tmpfs"`; `/run/rfs/bb` on a ramfs mounted for the test refused, see below |
| 5 | slot B booted to login, all units started; the agent attested (`counter=137405399044`, a new epoch); 0 SELinux denials in the journal of the boot; in `audit.log` after the last `DAEMON_START`, the two probe refusals and nothing else |

PCR 0 to 9 in `pcr-b.log` equal the slot B values of
`pcr-ref-imasig-20261109.json`; anyone can compare the two files. PCR 10
is not in the reference: it is checked by replaying the IMA log, which was
not done here.

The loaded policy holds four rules with `appraise_type=imasig`: the three
of this change and `appraise func=POLICY_CHECK appraise_type=imasig`, which
the kernel adds itself under `CONFIG_IMA_APPRAISE_REQUIRE_POLICY_SIGS=y`.

Before the change, on the image then on the board: 5768 `security.ima`
values of type `03` (signature) under `/usr`, `/opt` and `/etc` (symlinked
files counted once per path), none of type `01`, `02` or `04` (digest); of
4936 regular files, four carry no `security.ima`, all data that is never
executed (three systemd slice units and `/etc/machine-id`). Nothing on
`/data` carried `security.ima`. No ramfs was mounted. That is why requiring
a signature broke nothing on this image.

## What this shows and what it does not

- The development IMA signer is public by design (`pki/README.md`). Anyone
  can sign a file this image accepts. These results show that the policy
  and the signed root file system work together and that a digest is no
  longer enough; they do not show that a file came from TactiQ. A
  production image carries no IMA policy.
- The ramfs refusal left no record in `audit.log` or the journal. In the
  kernel source of this build, `ima_appraise.c` line 512 returns early for
  an inode without xattr support (`!(inode->i_opflags & IOP_XATTR)`),
  before the signature is checked; that this branch writes no audit record
  is not established here. A refusal on ramfs is therefore not visible to
  anyone reading the audit log.
- Execution of code from a memfd (shmem, the tmpfs magic) was not tested.
  Nothing on this image failed to start, so nothing on it does that, but a
  program that does will now be refused.
- Measurement still exempts tmpfs and ramfs whole (`dont_measure`): a
  signed program copied to `/tmp` with its `security.ima` passes appraisal
  and its execution is not in the measurement list. It can only be code
  the image already carries signed; the gap is in the log, not in what can
  run.
- One board, one boot of the new image.
