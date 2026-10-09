# Measurement: Rock 5T stage 1 boot

Date: 2026-10-09. Board: Radxa ROCK 5T (RK3588, 8 GiB LPDDR5, 58.3 GiB
eMMC), no TPM module fitted. Console: UART2 at 1500000 8N1, read with
PuTTY and copied out with "Copy All".

Purpose: establish whether TactiQ OS boots on `tactiq-rock5t` at all.
Stage 1 is boot without a TPM and without measured boot; the TPM, the
devicetree changes for it and a PCR reference for this board are stage 2.

## Inputs

| | |
|---|---|
| Tree | branch `rock5t/stage1` at `5b940e7`, one commit on top of `rc14/layer-shift` at `517a3ed` |
| MACHINE | `tactiq-rock5t` |
| Image recipe | `tactiq-image-dev` |
| Image | `tactiq-image-dev-tactiq-rock5t.rootfs-20261009025611.wic`, 9 139 405 824 bytes, sha256 `119559176a9fb0ee6fa113a4e8ef1e2407d36a67e36480f248f9948c8cedd975` |
| Transfer file | `.wic.gz` of the same image, sha256 `c20b1926d5352fda67805eed495031cfaf2018691207b43841f6733702f9478a`, identical on the build host and on the USB stick read from the board |
| Loader | U-Boot v2026.10 from `u-boot-rockchip_2026.10.bb`, `rock5b-rk3588_defconfig` pinned to the 5T devicetree by `rock5t.cfg` |
| Kernel | `linux-yocto` 6.18.52 |
| FIT key | development key `dev-fit`, not a release key |

The image was written to the eMMC (`mmcblk0`) with `dd` from the board
itself, running the vendor Radxa image from microSD. The microSD card was
removed before the first boot of the written image, so the BootROM could
not fall back to it. The eMMC was not read back and compared with the image
after writing; the checks below cover what booted, not every written byte.

## Raw output

`logs/rock5t-stage1-uart-20261009.log`, listed in `SHA256SUMS`.

It is the PuTTY scrollback as copied, with carriage returns removed and
nothing else changed. It starts in the middle of the first boot, at kernel
time `0.153535`: the loader and the start of that boot had already left the
buffer. It then holds the rest of the first boot, the commands run on it, a
`reboot`, the second boot in full from DDR initialisation to the login
prompt, and the commands run after it.

## Result

Second boot, loader:

    U-Boot SPL 2026.10 (Oct 05 2026 - 21:35:33 +0000)
    Model: Radxa ROCK 5T
    Reading from MMC(0)... Loading Environment from MMC... OK
    TactiQ: booting slot A (BOOT_A_LEFT now 2)
       Using 'conf-rk3588-rock-5t.dtb' configuration
       Verifying Hash Integrity ... sha256,rsa2048:dev-fit+ OK

The loader reads the environment saved on the first boot, picks slot A and
verifies the FIT configuration signature with the development key before
loading the kernel and the 5T devicetree.

Kernel:

    [    0.000000] Linux version 6.18.52-yocto-standard-00161-ga7cab2016d65 ...
    [    0.000000] Machine model: Radxa ROCK 5T

Root filesystem, read on the running system after the second boot:

    0 889552 verity 1 179:2 179:2 4096 4096 111194 111194 sha256 ...
    0 889552 verity V

The root is a dm-verity target and its status is `V`: no block read so far
failed verification.

SELinux and IMA, same session:

    SELINUX Enforcing
    IMA     appraise-rules=4 measure-rules=7 cmdline=none

An IMA policy with 4 appraise and 7 measure rules is loaded. The IMA mode
(enforce or log) cannot be read from `/sys` and is not established here;
the absence of `ima_appraise` on the command line does not mean IMA is off.
Without a TPM the kernel reports `ima: No TPM chip found, activating
TPM-bypass!`, so measurements are not extended into any PCR.

Repeat boot: the system was rebooted with `reboot` and reached the login
prompt again on slot A.

## Not working on this board, expected for stage 1

- `tactiq-agent` does not start:
  `Failed to set up mount namespacing: /dev/tpm0: No such file or directory`.
  The unit binds `/dev/tpm0` and `/dev/tpmrm0`, and there is no TPM.
- No measured boot and no PCR reference for this board.
- The machine-id is random (`Initializing machine ID from random
  generator.`). The `vm,uuid` fixup (`0006`) is not applied on the 5T; the
  reason is recorded in the comment above the `:tactiq-rock5t` overrides in
  `u-boot-rockchip_2026.10.bb`.

## Defects seen, cause not established

- First boot only: `tactiq-log-setup` reports
  `mkdir: can't create directory '/data/': Permission denied` and
  `completed with errors`. The second boot shows no such lines. No AVC
  denial was found in `dmesg`. Whether the same happens on a freshly
  written Rock 5A data partition has not been checked.
- During `reboot`: `Failed unmounting Persistent journal on the TactiQ data
  partition.`, `Failed unmounting /var/volatile.` and
  `watchdog: watchdog0: watchdog did not stop!`. Not investigated.
- `GPT:Alternate GPT header not at the end of the disk.`: the image is
  smaller than the eMMC and the backup GPT sits at the end of the image.

## What this does not show

Slot B boot, a RAUC update, a boot with release keys, the loader contents
on the eMMC compared byte for byte with the build, and anything that needs
a TPM.

## When this stops holding

A change to `u-boot-rockchip_2026.10.bb` or `rock5t.cfg`, to
`tactiq-rock5t.conf`, to the kernel version or the `rk3588-rock-5t`
devicetree, or a different board revision. Any of these needs a new boot
on the board and a report that names this one.
