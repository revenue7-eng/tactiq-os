# Design decision: rootfs dm-verity under A/B OTA

Status: **decision recorded, not implemented.**
Date: 2026-08-17. Tree: `main` @ `8551899`.

This document exists to fix an architectural decision before code is written.
It describes intent. It does not describe the current behaviour of the system.
Nothing here may be cited as a property of any shipped release.

---

## 1. Scope

The website status line reads:

> `dm-verity : signed FIT images and dm-verity, in progress`

That line collapses three independent mechanisms at three different levels of
readiness. This document covers only the second and third.

| # | Mechanism | State |
|---|-----------|-------|
| 1 | dm-verity over the RAUC update bundle | working; `RAUC_BUNDLE_FORMAT = "verity"`, `recipes-core/bundles/tactiq-bundle.bb:20`. Recorded in `security/coverage-rock5a.v2.1.0-rc6.yaml:210` and `rc7.yaml:315` with exception **EX-0005 (bundle-level dm-verity only)**. Protects the update artefact, not the root filesystem at boot. |
| 2 | dm-verity over rootfs | kernel support present only (§2). No hash tree, no enforcement. |
| 3 | Signed FIT | absent. Never enabled at any point (§2.2). |

---

## 2. Established state

### 2.1 Kernel support (PR #119, merged)

`recipes-kernel/linux/linux-yocto/tactiq-verity.cfg`, referenced from
`linux-yocto_%.bbappend` (SRC_URI, line 20). Options, all `=y`:

`CONFIG_MD`, `CONFIG_BLK_DEV_DM`, `CONFIG_DM_INIT`, `CONFIG_DM_VERITY`,
`CONFIG_DM_VERITY_VERIFY_ROOTHASH_SIG`

Confirmed by artefact: build for `MACHINE=tactiq-rock5a`, all five present in the
resulting `.config`; `log.do_kernel_configcheck` clean with respect to this
fragment. **Not tested on hardware.**

`CONFIG_DM_INIT` is required because `CONFIG_BLK_DEV_INITRD=n`
(`tactiq-security.cfg`). Without an initramfs there is no userspace stage for
`veritysetup`; the verity device must be constructed by the kernel itself from
`dm-mod.create=`. Without `DM_INIT` the fragment would still build and the root
filesystem would mount directly, unverified, with no error.

### 2.2 Signed FIT was never enabled

`UBOOT_SIGN_ENABLE`, `UBOOT_SIGN_KEYDIR` and `CONFIG_FIT_SIGNATURE=y` appear
only in the prose of `RELEASE_INTEGRITY.md` (lines 294, 295, 314), with
`TACTIQ_OS_FIT_SIGNING_KEY (placeholder; final name TBD)`. No match in any
`.bb`, `.bbappend`, `.inc`, `.conf` or `.bbclass`.

`git log` on `conf/machine/include/tactiq-arm64-uboot-base.inc` shows four
commits (`1d9c9a7`, `f0de5b7`, `8ce7844`, `ab37fc2`), all concerning
extlinux/wic. `KERNEL_CLASSES ?= ""` has been in place since rc4 and has never
changed. The comment "rc5 Stage 1: FIT disabled for extlinux identity-test.
Re-add in rc5/rc6" records an intention, not a revert. There is nothing to
restore; this is new work.

Current boot path: extlinux, bare `Image` + dtb + `extlinux.conf` on `boot_a`.

### 2.3 Slot layout (`recipes-core/bundles/tactiq-bundle.bb`)

```
RAUC_BUNDLE_SLOTS       = "rootfs boot"     # line 28
RAUC_SLOT_rootfs        = "tactiq-image"    # line 29
RAUC_SLOT_rootfs[fstype]= "ext4"            # line 30
RAUC_SLOT_boot          = "tactiq-boot-image"        # line 33
RAUC_SLOT_boot[file]    = "tactiq-boot-image.ext4"   # line 35
```

Two facts follow, and both are load-bearing for everything below:

1. The rootfs slot receives a **raw ext4 image**, not an unpacked archive.
   A verity hash tree is computed over a specific byte sequence; had the slot
   been populated by extracting a tarball, the installed filesystem would not
   reproduce the image the hash was computed from, and rootfs verity could not
   be built at all.
2. The boot slot is **itself part of the OTA**, and both slots travel in one
   bundle. rootfs and boot are therefore installed as an atomic pair.

---

## 3. The problem

A verity root hash must reach the kernel at boot, and must not be attacker-
controllable. Today the root hash would live in bootargs, and under extlinux
that means `extlinux.conf` - a text file on `boot_a`, editable by anything with
write access to that partition.

**Without a signed boot object, rootfs verity protects against flash corruption
but not against substitution.** This is why the two mechanisms are named on one
status line: neither is useful alone.

---

## 4. Where the root hash is anchored

### Option A - inside a signed FIT

Bootargs become part of the signed FIT `/configurations`. U-Boot verifies the
FIT signature against the public key in its control FDT before using anything
from it. The root hash becomes immutable content of a signed artefact.

### Option B - separate signed blob, assembled by a U-Boot script

Requires a trusted boot script, which must itself be signed. Strictly more
machinery than A for the same guarantee.

### Option C - `DM_VERITY_VERIFY_ROOTHASH_SIG`, kernel-verified root hash

Superficially the most attractive: the kernel verifies a signature over the root
hash against its own keyring, so tampering with the hash in `extlinux.conf`
would fail verification and no signed FIT would be needed.

**Structurally unavailable in this configuration. Confirmed against kernel
source at tag v6.18**, the kernel line in this tree:

- `drivers/md/dm-verity-verify-sig.c:38` -
  `key = request_key(&key_type_user, key_desc, NULL);`
  The root hash signature is not passed in the target table. It is retrieved
  from a key of type `user` that must already exist in a keyring. If absent,
  `request_key` falls through to an upcall to `/sbin/request-key`, which is also
  userspace.
- `drivers/md/dm-init.c:320` - `late_initcall(dm_init_init);`
  Devices declared by `dm-mod.create=` are constructed during kernel init,
  before `init` is executed.

With `CONFIG_BLK_DEV_INITRD=n` there is no stage between those two points at
which a userspace process could add the key.

Note precisely where the obstacle lies. The *verification* keys may be builtin:
`verify_pkcs7_signature` resolves against the builtin, secondary or platform
keyring (same file, lines 130-142). The obstacle is the *signature blob itself*,
whose only path into the kernel is a userspace-populated `user` key. This closes
the option more firmly than a missing image-stage step would.

Recorded explicitly so the option is not re-examined from scratch. Should an
initramfs ever be introduced, this decision must be revisited - the option is
closed by the absence of a userspace stage, not by anything intrinsic to verity.

### Decision

**Option A.** Options B and C are closed for the reasons above.

---

## 5. How A/B resolves

Because rootfs and boot ship in the same bundle (§2.3), each bundle carries a
FIT embedding the root hash of *its own* rootfs. The pairing is structural, not
procedural - it cannot drift. Root hashes differ between slot A and slot B
because the slots hold different *versions*, not because they are different
slots.

One genuine constraint remains. A single bundle carries one boot image, which is
installed into whichever slot is inactive, so **the same signed FIT must boot
from either slot** - while `root=` inside `dm-mod.create=` names a different
physical partition in each. Bootargs are inside the signature and cannot be
rewritten at install time.

**Resolution: one `.itb` containing two signed `/configurations`**, differing
only in the partition reference, carrying the same root hash. U-Boot selects the
configuration by name from the slot variable RAUC already manages for A/B.

Consequences:

- `UBOOT_EXTLINUX_ROOT ?= "root=PARTLABEL=__RAUC_PART__"`
  (`linux-yocto_%.bbappend`, section 3) is removed. RAUC no longer rewrites a
  bootarg; it selects a signed configuration. The problem of rewriting a
  parameter *inside* `dm-mod.create=` does not arise.
- `root=/dev/dm-0` in both configurations; the real partition moves inside
  `dm-mod.create=`.

Security property to state plainly: an attacker who alters the selection
variable can only switch between two legitimately signed configurations. That is
not a compromise of this mechanism. Rollback to an older signed version is a
distinct threat (rollback protection) and is **out of scope for this document**.

---

## 6. Build-system consequences

1. **`tactiq-boot-image` acquires a dependency on `tactiq-image`.** The root hash
   is an output of `veritysetup format` over the final ext4 image and is needed
   before the FIT is assembled. This inter-image ordering must be declared
   explicitly; it must not be left to default task scheduling.
2. **Hash tree placement - decided: appended to the ext4 image.** The slot
   artefact becomes one byte sequence, data followed by hash tree, written to
   the partition by a single raw copy. `dm-mod.create=` addresses the tree by
   offset within the same device.

   The alternative - a separate hash partition per slot - is rejected on
   architectural grounds, not convenience. Separate partitions can be written
   independently, which means the correspondence between a root filesystem and
   its hash tree becomes something the update process must get right. Appending
   makes divergence impossible to express: there is one artefact and one write,
   so a filesystem cannot be installed without its tree, and a tree cannot be
   replaced without its filesystem. The same reasoning as `parent=rootfs.N` in
   `system.conf` (§7), applied one level down.

   Cost: the rootfs partition must grow to hold the tree. For SHA-256 over
   4096-byte blocks the overhead is on the order of one hash block per 128 data
   blocks, plus the verity superblock - but the figure must be computed from
   `veritysetup format` output for the actual image, not assumed from this
   estimate, and the wks template sized against the measured value.
3. **`dm-mod.create=` carries per-build numeric parameters** (data block count,
   hash offset), both outputs of `veritysetup format`. FIT generation is
   therefore not a static template.
4. **Bootloader recipe - established.** U-Boot is built from source, not shipped
   as a vendor blob: `meta-tactiq-bsp-rockchip/recipes-bsp/u-boot/u-boot-rockchip_2024.07-kwiboo.bb`,
   with `PREFERRED_PROVIDER_virtual/bootloader = "u-boot-rockchip"`
   (`tactiq-rockchip-rk3588.inc:31`) and `UBOOT_MACHINE = "rock5a-rk3588s_defconfig"`
   (`meta-tactiq-bsp-rockchip/conf/machine/tactiq-rock5a.conf:17`). Option A is
   therefore implementable. The layer split dictates placement: `UBOOT_SIGN_*` is
   vendor-agnostic and belongs in core (`tactiq-arm64-uboot-base.inc`), while
   `CONFIG_FIT_SIGNATURE=y` is a config fragment for one bootloader build and
   belongs in `meta-tactiq-bsp-rockchip`, alongside the existing `env-mmc.cfg`
   and `boot-ab.cfg`.
5. **Moving `boot_a` from extlinux to `.itb`** touches `tactiq-boot-image.bb`
   (SELinux labelling via setfiles) and the wks template. This is the most
   invasive step in the sequence.

---

## 7. Established: U-Boot is outside the update perimeter

`recipes-core/rauc/files/system.conf` declares four slots and no bootloader slot:

```
[system]
compatible=TactiQ OS Rock5A
bootloader=uboot
bundle-formats=-plain

[slot.rootfs.0]  device=/dev/disk/by-partlabel/rootfs_a  type=ext4  bootname=A
[slot.rootfs.1]  device=/dev/disk/by-partlabel/rootfs_b  type=ext4  bootname=B
[slot.boot.0]    device=/dev/disk/by-partlabel/boot_a    type=ext4  parent=rootfs.0
[slot.boot.1]    device=/dev/disk/by-partlabel/boot_b    type=ext4  parent=rootfs.1

[keyring]  path=/etc/rauc/root-ca.pem  check-purpose=codesign-rauc
```

Three consequences.

**U-Boot is never updated by RAUC.** Its control FDT, which would hold the FIT
public key, therefore cannot be replaced through OTA - and equally cannot be
rotated through OTA. This is the root of trust for the whole scheme and it is
outside the update path by construction. Recorded as a deliberate property.

**The rootfs/boot pairing is enforced on the device, not only at build time.**
`parent=rootfs.N` makes each boot slot a child of its rootfs slot. The pairing
asserted in §5 holds on both sides.

**Slot selection runs through the U-Boot environment** (`bootloader=uboot`,
`bootname=A`/`B`), where `boot_ab` iterates `BOOT_ORDER` and sets `rauc_slot` and
`rauc_part`. The configuration-selection mechanism proposed in §5 therefore
extends an existing mechanism rather than introducing one.

`bundle-formats=-plain` additionally means plain bundles are rejected at install
time; only verity/crypt formats are accepted.

### 7.1 U-Boot environment integrity - established, and load-bearing

The environment is stored in raw MMC sectors and must remain writable.

`meta-tactiq-bsp-rockchip/recipes-bsp/u-boot/files/env-mmc.cfg`:

```
CONFIG_ENV_IS_IN_MMC=y
CONFIG_ENV_OFFSET=0xB00000
CONFIG_ENV_SIZE=0x8000
CONFIG_SYS_MMC_ENV_DEV=1
```

`.../files/boot-ab.cfg` compiles a default environment into the binary:

```
CONFIG_USE_DEFAULT_ENV_FILE=y
CONFIG_DEFAULT_ENV_FILE="tactiq-boot.env"
```

`.../files/tactiq-boot.env` defines `bootcmd=run boot_ab`, and `boot_ab` iterates
`BOOT_ORDER`, decrements `BOOT_A_LEFT`/`BOOT_B_LEFT`, calls `env save`, sets
`rauc_slot` and `rauc_part`, and boots via
`sysboot mmc 1:1 ... /boot/extlinux/extlinux.conf` for slot A and `mmc 1:3` for
slot B.

**The attack this enables.** `bootcmd` lives in the compiled-in default
environment, but with `CONFIG_ENV_IS_IN_MMC` the saved environment read from MMC
overrides the built-in default. Anything able to write raw sectors at offset
`0xB00000` from the running system can replace `bootcmd` outright - booting a
bare kernel image directly and never invoking `bootm`, so FIT signature
verification never runs. A signed FIT does not constrain what the device boots
while this holds.

**The environment cannot simply be made read-only.** `boot_ab` calls `env save`
on every boot to persist the bootcount decrement. Write access is load-bearing
for A/B itself.

**Resolution: `CONFIG_ENV_WRITEABLE_LIST`.** Confirmed present in U-Boot v2024.07
(`env/Kconfig:759`), the version in this tree. Only variables carrying an
explicit `w` flag may be written, modified or imported at runtime; nothing else
can be created or imported. It selects `ENV_APPEND`, so the built-in hash table
is never dropped and reloaded from imported data - the saved environment can no
longer override `bootcmd`.

The writeable list covers only variables that must survive `env save` across a
reboot:

| Variable | Written by |
|---|---|
| `BOOT_ORDER` | RAUC (`fw_setenv`) |
| `BOOT_A_LEFT` | `boot_ab` at boot; RAUC on mark-good |
| `BOOT_B_LEFT` | `boot_ab` at boot; RAUC on mark-good |

`rauc_slot` and `rauc_part` are set by `boot_ab` at runtime rather than
imported, so they need no flag. The option restricts imports, not writes:
runtime `setenv` is unaffected.

`CONFIG_ENV_ACCESS_IGNORE_FORCE` (`env/Kconfig:767`) is set alongside, so
`env set -f` cannot override the access flags.

Implemented on branch `uboot/env-writeable-list`, commit `ac871af`. Build-side
verification for `MACHINE=tactiq-rock5a`: the final U-Boot `.config` carries
`CONFIG_ENV_WRITEABLE_LIST=y`, `CONFIG_ENV_ACCESS_IGNORE_FORCE=y` and
`CONFIG_ENV_APPEND=y` (the last via `select`, confirming the option took
effect); `u-boot-initial-env` contains
`.flags=BOOT_ORDER:sw,BOOT_A_LEFT:dw,BOOT_B_LEFT:dw`. Not yet verified on
hardware.

## 8. Remaining open questions

1. Whether the FIT signing key shares the PKI hierarchy under `pki/dev/` or is a
   separate chain. Note that the RAUC development private keys are public by
   design (`tactiq-bundle.bb:6-9`); the FIT signing key is a different trust
   chain and that distinction must survive into production key management.
2. `TACTIQ_BOOT_METHOD` and `TACTIQ_AB_ENABLED`
   (`tactiq-arm64-uboot-base.inc:33,36`) are declared but read by nothing in the
   tree - no recipe, class or config consumes either. A/B works regardless,
   through `fw_setenv` on the RAUC side. When `fit-signed` is implemented,
   `TACTIQ_BOOT_METHOD` must either be wired up or removed; leaving a third
   declaration that describes intent without a mechanism repeats the
   `RELEASE_INTEGRITY.md` problem in §2.2.

---

## 9. Claims that may not be made

Until the corresponding artefact exists, none of the following may appear in the
website status line, coverage manifests, release notes, the manuscript, or any
public material:

- "rootfs verified", "verity enforced", or any equivalent - no hash tree is
  generated and no root hash reaches bootargs
- any property attributed to `DM_VERITY_VERIFY_ROOTHASH_SIG`, which is inert
- any statement about boot behaviour on hardware; none has been observed

What may currently be said: kernel support for rootfs dm-verity is present and
confirmed in the built configuration; enforcement is not implemented. Bundle-level
dm-verity is separate, working, and already recorded with exception EX-0005.

---

## 10. Order of work

1. `CONFIG_ENV_WRITEABLE_LIST` + `CONFIG_ENV_ACCESS_IGNORE_FORCE` with the
   writeable list (§7.1) - **built, pending hardware verification**
2. Hash tree generation at image stage (§6.2), with partition sizing taken from
   measured `veritysetup format` output
3. `UBOOT_SIGN_*` in `conf/machine/include/tactiq-arm64-uboot-base.inc`,
   `CONFIG_FIT_SIGNATURE=y` fragment in `meta-tactiq-bsp-rockchip`,
   `KERNEL_CLASSES = "kernel-fit-image"`
4. Two-configuration FIT assembly
5. Move `boot_a` from extlinux to `.itb`
6. Hardware verification

A full kernel rebuild runs about 2.5 hours and any `SRC_URI` change defeats
sstate; step 1 is cheap by comparison and can be validated on its own.

Step 5 is the point of no return for a given flash: devices declared by
`dm-mod.create=` are constructed at `late_initcall`, before userspace exists, so
a hash mismatch or a malformed FIT fails where there is no console userspace and
no diagnostics. Confirm a working re-flash path before attempting it.
