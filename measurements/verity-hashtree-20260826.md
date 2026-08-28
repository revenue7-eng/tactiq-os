# Measurement: rootfs dm-verity hash tree

Date: 2026-08-26. Host: build host (x86_64), not the board.
Purpose: supply the measured figure required by
`docs/design/verity-fit-ab.md` §6.2, which states the partition must be
sized against `veritysetup format` output rather than an estimate.

## Inputs

| | |
|---|---|
| Image | `tactiq-image-tactiq-rock5a.rootfs-20260826135053.ext4` |
| Image size | 363 859 968 bytes |
| Tool | `veritysetup 2.8.6`, flags: BLKID KEYRING KERNEL_CAPI HW_OPAL |
| Tool origin | `cryptsetup-native` from this build tree, not the host distribution |
| Parameters | `--data-block-size=4096 --hash-block-size=4096` (explicit, not defaulted) |

The image was copied to a scratch directory first; the artefact in
`tmp/deploy` was not used as either input or output.

Note on provenance: this image was produced by a build with the work tree
on branch `docs/verity-fit-ab-state-20260826`. The figures below depend on
the size and layout of the ext4 image only, not on U-Boot configuration.

## Result

```
Data blocks:            88833
Data block size:        4096
Hash blocks:            702
Hash block size:        4096
Hash algorithm:         sha256
Hash device size:       2879488 bytes
```

Derived:

| | |
|---|---|
| Data blocks cross-check | 363859968 / 4096 = 88833 exactly |
| Hash device blocks | 2879488 / 4096 = 703 (702 tree + 1 superblock) |
| Combined artefact | 366 739 456 bytes = 349.75 MiB |
| Overhead over data | 0.79 % |

Root hash and salt are omitted deliberately: the salt defaults to random,
so both change on every run and neither is a property of the image.

## The §6.2 estimate is low

§6.2 estimates "one hash block per 128 data blocks". The tree is
multi-level:

    ceil(88833/128) = 695
    ceil(695/128)   = 6
    ceil(6/128)     = 1
    total           = 702

which matches the tool exactly. The estimate accounts for the bottom level
only and is short by 8 blocks (32 KiB). Small in absolute terms; recorded
because the document's own rule is that the figure comes from measurement.

## Partition sizing: no change required

`meta-tactiq-bsp-rockchip/files/wic/tactiq-ab-rockchip.wks.in:22` gives
`rootfs_a` 2048 MiB. The combined artefact is 349.75 MiB. The partition is
already oversized relative to the image and the hash tree does not change
that. The §10 step "wks template sized against the measured value" is
satisfied without modification.

## Open point found while measuring, not covered by the design document

**wic populates `rootfs_a` by generating a filesystem, not by copying the
measured image.**

    line 21: part --source rawcopy --sourceparams="file=tactiq-boot-image.ext4" ... --label boot_a
    line 22: part / --source rootfs --fstype=ext4 --label rootfs_a

A verity root hash is computed over one specific byte sequence. §2.3 of the
design document establishes that the RAUC rootfs slot receives a raw ext4
image, which is what makes rootfs verity possible at all - but that holds
for updates. First installation goes through wic, and line 22 does not copy
the image the hash was computed from.

Under verity, line 22 must become a `rawcopy` of the combined artefact
(data followed by hash tree), matching the form of line 21.

Consequence if this is missed: the first boot from a freshly flashed device
fails at `late_initcall`, where §10 records there is no userspace and no
diagnostics.

Not established: whether wic's generated filesystem differs from the deploy
image in ways beyond this, and whether `--source rawcopy` on this partition
interacts with `--no-fstab-update` currently set on line 22.

## Also not established

The salt is random by default. Reproducible builds require a fixed
`--salt=`, which is then identical across all devices. This is acceptable
for verity - the salt is not a secret - but it is a decision with
consequences and does not appear in the design document.

## Commands

    veritysetup format rootfs.ext4 hash.bin \
        --data-block-size=4096 --hash-block-size=4096

---

# Addendum: figures from the build, 2026-08-27

The measurement above was taken by hand with `veritysetup` on a scratch
copy. This section records what the build itself produces now that
`image_types_verity` is enabled and `IMAGE_FSTYPES` lists `verity`.

Different image, so the figures differ from the section above and neither
set supersedes the other. The 2026-08-26 image was 363 859 968 bytes
(88833 data blocks, 702 hash blocks); this one is smaller.

## Inputs

| | |
|---|---|
| Image | `tactiq-image-tactiq-rock5a.rootfs-20260827134257.ext4` |
| Produced by | the build, not by a manual `veritysetup` run |
| Branch | `feat/verity-hashtree-generation`, commit b220fe2 |
| Salt | fixed in `conf/distro/tactiq.conf`, no longer random |

## Result, read from `.ext4.verity-params`

```
VERITY_DATA_BLOCKS=87472
VERITY_DATA_BLOCK_SIZE=4096
VERITY_HASH_BLOCKS=691
VERITY_HASH_BLOCK_SIZE=4096
VERITY_HASH_ALGORITHM=sha256
VERITY_DATA_SECTORS=699776
VERITY_SALT=8a7b98d830ac3bf9daa968b9c322bc1e6d9300c632f8f610be59dd67d2c4d797
VERITY_ROOT_HASH=757319692c22f636839788c580d6dcc1390505d8748e4673e96641d0a674cb27
```

The salt in the artefact matches the value declared in the distro
configuration character for character. That resolves the "Also not
established" point above: the salt is now fixed, published in-tree, and
identical across devices by design.

## Cross-checks

| | |
|---|---|
| Tree arithmetic | ceil(87472/128)=684, ceil(684/128)=6, ceil(6/128)=1 → 691, matches the tool |
| Combined artefact | (87472+691) × 4096 = 361 115 648 bytes, matches `stat` exactly |
| Overhead over data | 0.79 % |
| Superblock | none — the total equals data + tree with nothing left over, confirming `--no-superblock` |

The 2026-08-26 section reports 703 hash blocks including a superblock. The
build output has no superblock, which is why the two are not comparable
block for block.

## The filesystem is not block-aligned

This does not appear in the section above and matters for partitioning.

    ext4 file size        358 282 240 bytes = 87471.25 blocks
    VERITY_DATA_BLOCKS    87472 → 358 285 312 bytes
    difference            3072 bytes

The tool rounded the data area up to a whole block and hashed the padded
region. `VERITY_DATA_BLOCKS` therefore describes an area, not the file.

Consequence for the wks change identified above: the rootfs partition must
receive the full 87472-block data area followed by the tree — that is, the
`.ext4.verity` artefact as one sequence. Writing the `.ext4` file and
stopping at its end leaves the final block short by 3072 bytes, dm-verity
reads a different byte sequence than was hashed, and the root hash does not
match. On a bench without verity enforcement the device still boots, so
this failure mode is invisible until verification is switched on.

## Artefact names

The class emits three files per image, suffixed onto the base type rather
than replacing it:

    <image>.ext4.verity          data area followed by the hash tree
    <image>.ext4.verity-params   shell-sourceable KEY=value pairs
    <image>.ext4.verity-info     the `veritysetup` header dump, human-readable

`<image>.verity` does not exist. Anything consuming these — wks, the RAUC
bundle, a signing step — must use the `.ext4.verity` form.

## Still not established

Nothing verifies this root hash. It is neither signed nor referenced by the
kernel command line, and no boot stage consumes it. The wks source and the
RAUC bundle still describe the plain ext4 image.
