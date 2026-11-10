# Development image: lockdown in confidentiality mode, enforced module signatures, no user namespaces, io_uring refused (2026-11-10)

## Questions

1. Is kernel lockdown active on the board, and in which mode?
2. Are unsigned kernel modules refused?
3. Can an unprivileged process create a user namespace?
4. Is io_uring available to processes?
5. Does the image boot and run without failed units or SELinux refusals?
6. Does a slot built in the development tree carry, in its device tree,
   the verity root hash of the root file system written next to it?

## Setup

- Board: the Rock 5A reference board `TACTIQ-BENCH-001`, rollback floor 2,
  development bootloader (`u-boot.itb` sha256 `f7e0a56d…`).
- Before this change: the kernel configuration carried
  `CONFIG_LOCK_DOWN_KERNEL_FORCE_NONE=y` and the command line set no
  `lockdown=`, so the lockdown LSM was built in but enforced nothing;
  `CONFIG_MODULE_SIG_FORCE` was unset and the command line carried no
  `module.sig_enforce=`; `CONFIG_USER_NS=y` was set explicitly in
  `tactiq-security.cfg`; `CONFIG_IO_URING=y`, the kernel default. Read from
  the `.config` of the development build and from `tactiq-security.cfg` on
  main `e123448`.
- The change:
  - `tactiq-security.cfg`: `# CONFIG_USER_NS is not set`. systemd
    sandboxing does not need user namespaces (PID 1 creates mount, PID and
    network namespaces as root), and no unit in the layer uses
    `PrivateUsers=`.
  - `tactiq-slot-dtb.bb`: `lockdown=confidentiality module.sig_enforce=1
    sysctl.kernel.io_uring_disabled=2` added to `TACTIQ_COMMON_BOOTARGS`,
    so they sit in `/chosen` of each slot device tree inside the signed
    FIT.
  - `tactiq-image.bb`: `do_deploy_verity_params` is no longer an sstate
    task (see question 6).
  - `image_types_bootext4.bbclass`: building the boot file system fails
    unless the FIT carries the root hash of the root file system of the
    same run.
- Built in the development tree from branch `kernel-lockdown-userns`
  (main `e123448` with this change) and tactiq-os-selinux
  `agent-vault-data-narrow` `09f41d6`, which is not the revision
  `integration/LAYERS.lock` pins. Kernel `6.18.52-yocto-standard`.
  Image stamp `20261110073428`; root hash
  `39192b725cff4697c0d4effe5590efea8508b54661bc2dee1742fb851461d7b5`;
  the boot file system sha256
  `87803e566729f41da0ca3586b82486a6b9443140516d6f080720a3febc71ad29`,
  the root file system (`.ext4.verity`, 458399744 bytes)
  `81099feaa2b51e3f9d5738d8c8d602478193117fb791c26ac344f6bdb23ab59a`.
- Delivery: from slot B, both partitions of slot A written with `dd` and
  read back to the sums above; `rauc status mark-active other`; cold start
  (power pulled).

## Files

| file | what |
| --- | --- |
| `a-verity-fail.log` | the first delivery: three boots of slot A ending in a kernel panic at verity, the fallback of U-Boot to slot B, and checks run on slot B (the old image there) |
| `pcr-match-a-verity-fail.log` | `pcr-match` after that fallback: the board matched the reference of the old slot B image |
| `deploy-verity-params.log` | the deploy directory after the first delivery: the published parameters (root hash `dc3773c9…`) against the parameters of the root file system actually in deploy (`c8863c26…`) |
| `write-and-boot-a.log` | the second delivery: the write of slot A from slot B, the switch, the boot of slot A and the checks |
| `lockdown-probes-a.log` | `sig_enforce` and a read of `/dev/mem` on slot A |
| `pcr-match-a.log` | `pcr-match` on slot A after the cold start |
| `pcr-ref-lockdown2-20261110.json` | the reference of this build, from `mk-pcr-reference.py` |

Sums of every file are in `../SHA256SUMS`.

## Results

| question | result |
| --- | --- |
| 1 | `/sys/kernel/security/lockdown` reads `none integrity [confidentiality]`; the kernel logs `Kernel is locked down from command line`; opening `/dev/mem` as root is refused, `Operation not permitted` |
| 2 | `/sys/module/module/parameters/sig_enforce` reads `Y`. No unsigned module was offered to the kernel, so the refusal itself is not observed here |
| 3 | `unshare -U true` as root fails, `unshare failed: Invalid argument`: the kernel has no user namespaces |
| 4 | `/proc/sys/kernel/io_uring_disabled` reads `2`, which refuses `io_uring_setup` to every process. No io_uring call was made |
| 5 | slot A booted to login; `systemctl --failed` lists 0 units; `tactiq-agent` and `agentgateway` active; 0 SELinux denials in the journal of the boot |
| 6 | the first delivery: no. The second: yes, see below |

PCR 0 to 9 in `pcr-match-a.log` equal the slot A values of
`pcr-ref-lockdown2-20261110.json`. PCR 10 is not in the reference.

## Question 6: the first delivery of slot A did not boot

The first build of this change was written to slot A and read back to the
sums of the files in deploy. All three boots of slot A ended in a kernel
panic before userspace (`a-verity-fail.log`):

    device-mapper: verity: 179:2: metadata block 111038 is corrupted
    EXT4-fs (dm-0): unable to read superblock

Block 111038 is the first block of the hash tree. The device tree in the
FIT carried root hash `dc3773c9…`; the root file system written next to it
has `c8863c26…` (`deploy-verity-params.log`). U-Boot then booted slot B,
as `boot_ab` is designed to.

Cause: `tactiq-slot-dtb` reads the parameters that
`do_deploy_verity_params` publishes to `DEPLOY_DIR_IMAGE`. That task was
an sstate task. When its signature matched, bitbake restored its output
from sstate without running `do_image_verity`, and the root file system is
not bit-reproducible, so the restored parameters belonged to a root file
system from an earlier run. The published file carries the timestamp
`00:43:30.000000000`, whole seconds, as restored files do; the root file
system in deploy is from `01:47:55`. After `bitbake -c cleansstate
tactiq-image-dev`, the published parameters were present again while
`do_image_verity` had not run, which is the same restore.

Fix in this change: `do_deploy_verity_params` is a plain task, so it only
copies the parameters of the root file system built in the same build
directory; and `do_image_bootext4` refuses to build when the FIT does not
carry the root hash of that root file system. The second build passed that
check; its boot file system carries one root hash, `39192b72…`, equal to
`VERITY_ROOT_HASH` of its root file system, and slot A booted.

The board refused the mismatched slot before userspace. Verity did what it
is for; the defect was that the build produced and deployed such a slot
without an error.

## What this shows and what it does not

- Lockdown does not stop a kernel exploit. Code that runs in the kernel is
  outside what any LSM enforces. What this change removes is the two most
  used entry points for an unprivileged process to reach such code (user
  namespaces, io_uring) and the ways for root to read or write kernel
  memory or load unsigned code into the kernel.
- `# CONFIG_IO_URING is not set` in `tactiq-security.cfg` has no effect:
  the symbol is only settable with `CONFIG_EXPERT`, and the built
  `.config` reads `CONFIG_IO_URING=y`. io_uring is refused at runtime by
  the command line, not compiled out. The line is left as it was built and
  is corrected with the next change to the kernel configuration, so that
  the kernel on the board is the one this tree describes.
- The image lists sixteen `nbd` devices, built into the kernel and unused
  on a board without a network. Not changed here.
- One board, one boot of the new image. The release image was not built.
