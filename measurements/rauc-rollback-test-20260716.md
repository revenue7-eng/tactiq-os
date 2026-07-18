# RAUC Rollback Test — 2026-07-16

## Summary

Rollback from corrupted slot B to healthy slot A verified on Rock 5A
hardware. The U-Boot boot-count mechanism exhausts three attempts, then
selects the working slot. Slot selection itself needs no operator action:
the boot-count logic runs in U-Boot, before the kernel.

The full cycle was not unattended in this test. `kernel.panic=N` was not
set on the image under test, so the board halted on each panic and was
power-cycled by hand three times (observation 4). Unattended operation
requires panic-reboot or a hardware watchdog.

Closed since this test: the production image now sets `kernel.panic=5` in
bootargs — see lines 124 and 166 of
`selinux-enforcing-boot-prod-20260717.log` in this directory. The watchdog
(Synopsys DesignWare watchdog0) is present but not yet enabled.

**Result: PASS**

---

## Hardware

- Board: Radxa Rock 5A (RK3588S)
- Storage: SD card (mmcblk1), GPT, 5 partitions
- Image: tactiq-image-dev, TactiQ OS 2.0.0
- Kernel: 6.18.24-yocto-standard
- SELinux: enforcing (mark-good path)
- UART: PuTTY COM3 1500000 baud

## Partition layout

| Partition   | PARTLABEL | Device      |
|-------------|-----------|-------------|
| boot_a      | boot_a    | mmcblk1p1   |
| rootfs_a    | rootfs_a  | mmcblk1p2   |
| boot_b      | boot_b    | mmcblk1p3   |
| rootfs_b    | rootfs_b  | mmcblk1p4   |
| data        | data      | mmcblk1p5   |

## Pre-conditions

System booted from slot A, both slots healthy:

```
root=PARTLABEL=rootfs_a rootwait rw rootfstype=ext4 earlycon rauc.slot=A console=tty1 console=ttyS2,1500000n8
BOOT_ORDER=A B
BOOT_A_LEFT=3
BOOT_B_LEFT=3
```

rootfs_b (`/dev/mmcblk1p4`) confirmed not mounted via `lsblk`.

## Procedure

### Step 1: Corrupt rootfs_b

```
root@tactiq-rock5a:~# dd if=/dev/urandom of=/dev/mmcblk1p4 bs=1M count=1 && sync && echo "rootfs_b corrupted"
1+0 records in
1+0 records out
rootfs_b corrupted
```

### Step 2: Set B as primary boot target

```
root@tactiq-rock5a:~# fw_setenv BOOT_ORDER "B A" && fw_setenv BOOT_B_LEFT 3 && fw_printenv BOOT_ORDER BOOT_A_LEFT BOOT_B_LEFT
BOOT_ORDER=B A
BOOT_A_LEFT=3
BOOT_B_LEFT=3
```

### Step 3: Reboot, observe three failed attempts

**Power cycle #1:** U-Boot decrements BOOT_B_LEFT (3→2), loads kernel
from boot_b, kernel attempts mount of rootfs_b:

```
Waiting for root device PARTLABEL=rootfs_b...
No filesystem could mount root, tried:
   ext4
VFS: Unable to mount root fs on "PARTLABEL=rootfs_b" or unknown-block(179,4)
User configuration error - no valid root filesystem found
Kernel panic - not syncing: Invalid configuration from end user prevents continuing
---[ end Kernel panic - not syncing: Invalid configuration from end user prevents continuing ]---
```

Board hangs (no `kernel.panic=N` configured). Manual power cycle.

**Power cycle #2:** Same kernel panic. BOOT_B_LEFT 2→1. Manual power cycle.

**Power cycle #3:** Same kernel panic. BOOT_B_LEFT 1→0. Manual power cycle.

### Step 4: Automatic fallback to slot A

After power cycle #3, U-Boot finds BOOT_B_LEFT=0, skips slot B,
boots slot A. System reaches login prompt. RAUC mark-good restores
BOOT_A_LEFT=3.

```
[ OK ] Finished RAUC Good-marking Service.
TactiQ OS 2.0.0 tactiq-rock5a ttyS2
```

### Step 5: Verify final state

```
root@tactiq-rock5a:~# cat /proc/cmdline && echo "---" && fw_printenv BOOT_ORDER BOOT_A_LEFT BOOT_B_LEFT
root=PARTLABEL=rootfs_a rootwait rw rootfstype=ext4 earlycon rauc.slot=A console=tty1 console=ttyS2,1500000n8
---
BOOT_ORDER=B A
BOOT_A_LEFT=3
BOOT_B_LEFT=0
```

## Observations

1. **BOOT_B_LEFT=0** — three attempts exhausted, slot B excluded from boot.
2. **BOOT_A_LEFT=3** — mark-good restored after successful boot on A.
3. **BOOT_ORDER=B A** — unchanged; U-Boot skips B based on LEFT counter,
   not BOOT_ORDER removal. Design choice: slot re-enters rotation only
   after a successful `rauc install` restores LEFT.
4. **No `kernel.panic=N`** — board hangs after panic, requires manual power
   cycle. For production: add `kernel.panic=5` to bootargs, or configure
   hardware watchdog (Synopsys DesignWare watchdog0 present, timeout 1m29s,
   observed in shutdown log). Not a rollback mechanism defect — the
   boot-count logic is in U-Boot, which runs before kernel.
5. **Fallback path does not reset BOOT_ORDER** — the "no valid slot" branch
   (`BOOT_A_LEFT=0 AND BOOT_B_LEFT=0`) resets both LEFT to 3 and reboots.
   This prevents permanent brick but means a double-corruption scenario
   enters an infinite reboot loop. Acceptable for field-replaceable
   devices; document as known behavior.

## Boot script reference

Source: U-Boot environment variable `boot_ab`, invoked by `bootcmd=run boot_ab`.
Verified via `fw_printenv` on hardware (2026-07-16).

Key logic: iterate BOOT_ORDER, first slot with LEFT > 0 is selected,
LEFT decremented, env saved, then `sysboot` loads kernel via per-slot
`extlinux.conf` (boot_a = mmc 1:1, boot_b = mmc 1:3). If no slot
qualifies, drops to U-Boot prompt.

Note: `meta-rockchip/dynamic-layers/rk-rauc-demo/recipes-bsp/u-boot/files/boot.cmd.in`
is not used in the current build — no `boot.scr` is present on the
boot partition.
