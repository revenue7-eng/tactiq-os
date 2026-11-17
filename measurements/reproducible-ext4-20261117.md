# Development build: a rebuilt root file system gives the same ext4 and verity root hash (2026-11-17)

## Question

When the root file system is built again from the same inputs, is the
ext4, and with it the verity root hash, the same as before?

If it is not, `tactiq-slot-dtb` and the FIT, restored from sstate with the
root hash of the earlier run, no longer match the new root file system, and
the check from #310 stops `do_image_bootext4`. That happened after the
kernel rollback in `cve-status-check-kernel-20261113.md` (Limits) and again
on 2026-11-16 in the same build directory.

## Cause

`oe_mkext234fs` in oe-core runs `mkfs.ext4` and then `fsck.ext4 -pfD` and
fixes none of their sources of variation: `mkfs` picks a random filesystem
UUID and directory hash seed and writes the current time into the
superblock, and `fsck` writes the current time again (last write, last
checked). Outside bitbake, with e2fsprogs 1.47.0, two runs over one
directory differed without fixed values, still differed with only the
`mkfs` values fixed (the `fsck` times), and were byte-identical with
`-U`, `-E hash_seed`, `E2FSPROGS_FAKE_TIME` and `E2FSCK_TIME` set.

## Change

`recipes-core/images/tactiq-image.bb` (which `tactiq-image-dev.bb`
requires): `EXTRA_IMAGECMD:ext4` passes a fixed UUID and hash seed
(`TACTIQ_ROOTFS_FS_UUID`), and the recipe exports `E2FSPROGS_FAKE_TIME` and
`E2FSCK_TIME` from `REPRODUCIBLE_TIMESTAMP_ROOTFS`. Nothing reads the
UUID: the wks copies the partition raw and the kernel mounts `/dev/dm-0`.

## Setup

- Build directory `dev-build-rc11`, `MACHINE = "tactiq-rock5a"`, image
  `tactiq-image-dev`, layer at `main` `3508373` plus the change above
  (branch `image/reproducible-ext4`, `4e90d58`), e2fsprogs 1.47.4 from
  oe-core `2285da0`.
- Run 1: `bitbake tactiq-image-dev`. The change alters the image recipe, so
  the root file system and everything after it were built.
- Run 2: `bitbake -c cleansstate tactiq-image-dev`, then
  `bitbake tactiq-image-dev`. Nothing else changed between the runs, so the
  root file system was built again with the same inputs, while
  `tactiq-slot-dtb` and the FIT kept the root hash of run 1. This is the
  case that used to stop the build.

## Files

| file | what |
| --- | --- |
| `run1-root-hash.txt` | `VERITY_ROOT_HASH` from the deployed verity parameters after run 1 |
| `run2-root-hash.txt` | the same after run 2 |
| `run2-task-order.txt` | image tasks from `log.task_order` of run 2 (`do_rootfs` to `do_image_bootext4`) |
| `ext4-superblock.txt` | `dumpe2fs -h` of the deployed ext4 after run 2: UUID, hash seed, times |

Sums of every file are in `SHA256SUMS`.

## Results

| run | root file system | verity root hash | `do_image_bootext4` |
| --- | --- | --- | --- |
| 1 | built | `75a2942a6fd6e053ea1c078fa009edfc662b4b62aa2275ec2c78fbfa0bb55049` | passed |
| 2 | built again (`do_rootfs` 10:12, `do_image_ext4` 10:22) | `75a2942a6fd6e053ea1c078fa009edfc662b4b62aa2275ec2c78fbfa0bb55049` | passed, with the FIT of run 1 |

The superblock carries the fixed UUID and hash seed
(`5e2f0d7a-1c3b-4f6e-9a8d-2b7c4e1f0a93`) and fixed times. The task log of
run 1 is not kept: the cleansstate before run 2 removed the image work
directory with it. That run 1 used the change is shown by `dumpe2fs` after
run 1, which read the same UUID.

## Answer

Yes. Built again from the same inputs, the root file system gave the same
root hash, and the boot partition was built with the FIT of the earlier
run without the cleansstate of `tactiq-slot-dtb`, `linux-yocto-fitimage`
and `tactiq-boot-image` that the rollback in
`cve-status-check-kernel-20261113.md` needed.

## Limits

- One machine, one build directory, packages from the same sstate. Whether
  another machine gives the same root hash is not shown here; that is a
  separate reproducibility check.
- Development image only. The production image takes the same settings
  from `tactiq-image.bb` and has no IMA signatures; it was not built here.
- The check from #310 stays. A change that alters the root file system
  without altering its inputs as bitbake sees them (a file read at build
  time outside the task signatures) would still give a new root hash with
  an old FIT, and that check still stops the build.
- The boot partition (`bootext4`) still gets a random UUID; it does not
  feed the root hash and is outside this question.
