# Reproducibility report — v2.1.0-rc6 (wrynose-independent, rock5a)

Generated 2026-07-30 by `scripts/mk-repro-report.py` from two
independent builds of the same tag. Raw per-file differences:
`wrynose-independent-20260730-file-hash-diff.txt` (same directory).

## Inputs

| | Build A | Build B |
| --- | --- | --- |
| Build id | `20260718162433` | `20260730092521` |
| SBOM | `sbom-rock5a.spdx.json` | `sbom-rock5a.spdx.json` |
| SBOM format | SPDX 3.x | SPDX 3.x |
| Files with SHA-256 | 38723 | 38723 |

## Top-level artifacts

| Artifact | Build A | Build B | Match |
| --- | --- | --- | --- |
| `buildinfo-rock5a.json` | `4263db81200ad20b…` | `94033be8bb36ddd5…` | no |
| `bundle-rock5a.raucb` | `721cf4a4a7a823e5…` | `-…` | no |
| `cve-rock5a.enriched.json` | `8cd91578b6b253fb…` | `-…` | no |
| `cve-rock5a.sbom-cve-check.yocto.json` | `25f5179748e57c0d…` | `aa9a02c63dccaa7f…` | no |
| `image-rock5a.wic.bmap` | `ad3c43d49543647f…` | `ad2d867283be40e4…` | no |
| `image-rock5a.wic.gz` | `1cd720910307b9ce…` | `9193d2193f749428…` | no |
| `kernel-rock5a.bin` | `fcb9b4c7802cde92…` | `6763fda487ef6274…` | no |
| `manifest-rock5a.txt` | `4b9ea5ebdfb1dd8d…` | `4b9ea5ebdfb1dd8d…` | yes |
| `rk3588s-rock-5a.dtb` | `ca8c3df8981094f7…` | `ca8c3df8981094f7…` | yes |
| `sbom-rock5a.spdx.json` | `d29a9f3fe3540639…` | `c40b18ceb4195f88…` | no |
| `testdata-rock5a.json` | `dfddd17fea423d4b…` | `d11acdc48fbf4472…` | no |

## Per-file result

| Class | Count |
| --- | --- |
| Compared (present in both) | 38718 |
| Identical | 38694 |
| Differing — rootfs content | 24 |
| Differing — image-level artifact | 0 |
| Differing — known volatile | 0 |
| Present only in A | 5 |
| Present only in B | 5 |

**Per-file content reproducibility: NOT ACHIEVED.**

24 file(s) differ in rootfs content:

- `/boot/Image-6.18.24-yocto-standard-00129-gb1ba5428513b`
- `/etc/tactiq-release`
- `/linux-yocto-6.18.24+git/.kernel-meta/cfg/merge_config_build.log`
- `/linux-yocto-6.18.24+git/.kernel-meta/hardware_frags.txt`
- `/linux-yocto-6.18.24+git/.kernel-meta/meta-series`
- `/linux-yocto-6.18.24+git/.kernel-meta/non-hardware_frags.txt`
- `/usr/lib/modules/6.18.24-yocto-standard-00129-gb1ba5428513b/kernel/crypto/af_alg.ko`
- `/usr/lib/modules/6.18.24-yocto-standard-00129-gb1ba5428513b/kernel/crypto/algif_rng.ko`
- `/usr/lib/modules/6.18.24-yocto-standard-00129-gb1ba5428513b/kernel/net/ipv4/netfilter/ip_tables.ko`
- `/usr/lib/modules/6.18.24-yocto-standard-00129-gb1ba5428513b/kernel/net/ipv4/netfilter/iptable_filter.ko`
- `/usr/lib/modules/6.18.24-yocto-standard-00129-gb1ba5428513b/kernel/net/ipv4/netfilter/iptable_mangle.ko`
- `/usr/lib/modules/6.18.24-yocto-standard-00129-gb1ba5428513b/kernel/net/ipv4/netfilter/iptable_nat.ko`
- `/usr/lib/modules/6.18.24-yocto-standard-00129-gb1ba5428513b/kernel/net/ipv4/netfilter/nf_defrag_ipv4.ko`
- `/usr/lib/modules/6.18.24-yocto-standard-00129-gb1ba5428513b/kernel/net/ipv4/netfilter/nf_reject_ipv4.ko`
- `/usr/lib/modules/6.18.24-yocto-standard-00129-gb1ba5428513b/kernel/net/ipv6/ipv6.ko`
- `/usr/lib/modules/6.18.24-yocto-standard-00129-gb1ba5428513b/kernel/net/ipv6/netfilter/ip6_tables.ko`
- `/usr/lib/modules/6.18.24-yocto-standard-00129-gb1ba5428513b/kernel/net/ipv6/netfilter/ip6table_filter.ko`
- `/usr/lib/modules/6.18.24-yocto-standard-00129-gb1ba5428513b/kernel/net/ipv6/netfilter/nf_defrag_ipv6.ko`
- `/usr/lib/modules/6.18.24-yocto-standard-00129-gb1ba5428513b/kernel/net/netfilter/nf_conntrack.ko`
- `/usr/lib/modules/6.18.24-yocto-standard-00129-gb1ba5428513b/kernel/net/netfilter/nf_nat.ko`
- `/usr/lib/modules/6.18.24-yocto-standard-00129-gb1ba5428513b/kernel/net/netfilter/x_tables.ko`
- `/usr/lib/modules/6.18.24-yocto-standard-00129-gb1ba5428513b/kernel/net/netfilter/xt_conntrack.ko`
- `/usr/lib/modules/6.18.24-yocto-standard-00129-gb1ba5428513b/kernel/net/netfilter/xt_state.ko`
- `/usr/lib/modules/6.18.24-yocto-standard-00129-gb1ba5428513b/kernel/net/netfilter/xt_tcpudp.ko`

5 file(s) exist only in build A, 5 only in build B.

## Method

File hashes are read from the SPDX documents of each build and compared
by path. No file in either build tree is read or modified by this tool.
Classification of a difference as image-level or volatile follows fixed
lists in `scripts/mk-repro-report.py`; every other difference is
reported as a content finding without interpretation.

This report supersedes nothing. Earlier reports in this directory keep
their original figures and dates.
