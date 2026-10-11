# U-Boot FIT verification and parsing vulnerabilities in the reference bootloader

| Field | Value |
|---|---|
| Advisory | 2026-10-08-u-boot-fit-verification |
| Component | U-Boot, recipe `u-boot-rockchip_2024.07-kwiboo` (Kwiboo fork `rk3xxx-2024.07`, commit `8cdf606e`), reference machine Rock 5A |
| Affected releases | v2.1.0-rc11, v2.1.0-rc12, v2.1.0-rc13 |
| Not affected | releases before the signed-FIT boot path (`9a29145`, #176): they boot the kernel without FIT signature verification, which is disclosed separately in `BOOT_CHAIN.md` |
| Fixed in | v2.1.0-rc14 (in the tree on `rc14/layer-shift`, see Remedy) |
| Upstream identifiers | CVE-2026-46728, BRLY-2026-037 to BRLY-2026-042, CVE-2024-57256, CVE-2024-42040, CVE-2026-29007, CVE-2026-29008, CVE-2026-29009 |

## Summary

The bootloader shipped in rc11, rc12 and rc13 verifies the signed kernel FIT
with U-Boot code that has publicly known vulnerabilities. All of them are in
upstream U-Boot; none is in TactiQ OS code. They were public before rc11 was
built. Our CVE manifests did not report them, because the manifests covered
the root filesystem only and the bootloader is not installed there.

## Issues

**CVE-2026-46728, FIT signature bypass.** U-Boot before 2026.04 builds the list
of nodes covered by a configuration signature from the `hashed-nodes`
property, which is itself not covered by the signature. A signed FIT can be
edited so that the signature still verifies over the original images while
U-Boot boots different ones. Our loader selects the configuration explicitly
per slot and the verification key is `required = "conf"`; neither prevents
this. The images that can be substituted include the device tree, and with it
the kernel command line and the dm-verity root hash it carries. Fixed upstream
by commit `2092322b`.

**BRLY-2026-037 to BRLY-2026-042.** Six flaws in U-Boot's FIT parsing reported by
Binarly. They are reached while U-Boot reads the untrusted image, before the
signature is checked. Binarly reports that two of them can be chained to code
execution; the other four cause denial of service. Fixed upstream in June 2026.

**CVE-2024-57256, ext4.** An integer overflow in `ext4fs_read_symlink` lets a
crafted ext4 filesystem overwrite U-Boot memory. Our loader reads the FIT from
the ext4 boot partition with `load` before any signature check. Fixed upstream
in U-Boot 2025.01-rc1 (commit `35f75d2a`).

**Network: CVE-2024-42040, CVE-2026-29007, CVE-2026-29008, CVE-2026-29009.** The
affected loaders were built with the U-Boot network stack. The boot path does
not use it; these are reachable only through U-Boot network commands.

## Impact in the TactiQ OS threat model

Every issue above needs the ability to write the boot partition or the boot
medium: root on the running system, or physical access to the eMMC.

On the reference platform that access already allows replacing the bootloader
itself, because the boot ROM does not verify the bootloader (stated in
`BOOT_CHAIN.md`). These vulnerabilities therefore give such an attacker no
capability they did not already have. What they remove is the assurance that
the FIT signature check was meant to add: against an attacker who can write
the boot partition, a passing signature check on rc11 to rc13 says nothing
about what was booted.

They become a separate, serious weakness on any platform where the bootloader
is verified by the stage below it.

Measured boot does not cover this class reliably. For CVE-2026-46728 an
unmodified U-Boot measures what it loads, so a substituted kernel or device
tree may show in PCR 0 and PCR 8; we have not tested this and make no claim
that it does. For the parsing flaws that lead to code execution inside U-Boot,
the measurements are produced by the compromised code and cannot be relied on.

## Remedy

In the tree for rc14 (`rc14/layer-shift`):

- `f5f1581`: backports of the CVE-2026-46728 fix and of the fixes for
  BRLY-2026-037 to BRLY-2026-042 to the Kwiboo 2024.07 bootloader.
- `9c27cb3`: backport of the CVE-2024-57256 fix; the network stack is removed
  from the bootloader (`net-off.cfg`), which removes the network CVEs with it.
- `faef716`: a recipe for mainline U-Boot v2026.10, which contains all of the
  upstream fixes above. It is not selected by default until it has booted on
  the reference board. Which of the two loaders rc14 ships will be stated in
  the rc14 release notes.
- `8781c03`: the U-Boot recipe produces its own CVE manifest. rc14 is to publish
  it alongside the image manifest.

Not covered yet: the Rockchip firmware blobs from rkbin (TF-A BL31 and the DRAM
initialisation binary) are not in any CVE manifest. They have no upstream CPE
to match against.

There is no fix for rc11 to rc13 short of updating the bootloader. Signed
release assets are not changed.

## Credit

Apple Security Engineering and Architecture reported the `hashed-nodes` issue
to the U-Boot and barebox projects. Binarly reported BRLY-2026-037 to
BRLY-2026-042. We became aware of these through Ahmad Fatoum's talk on FIT
security at Embedded Linux Conference Europe 2026.

## Timeline

| Date | Event |
|---|---|
| 2026-03 | barebox advisory for the `hashed-nodes` issue (CVE-2026-33243) |
| 2026-04 | U-Boot fix `2092322b`, released in 2026.04 |
| 2026-05-16 | CVE-2026-46728 published for U-Boot |
| 2026-06 | U-Boot fixes for BRLY-2026-037 to BRLY-2026-042 |
| 2026-10-08 | Issue identified in TactiQ OS; fixes committed to `rc14/layer-shift`; this advisory |
