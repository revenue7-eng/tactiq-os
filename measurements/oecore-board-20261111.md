# Development image: openembedded-core pinned to wrynose 2285da0 (2026-11-11)

## Questions

1. Does the image built from the new openembedded-core pin boot on the
   board, and does its FIT pass the rollback check?
2. Are the kernel and OpenSSL on the board the versions the build lists?
3. Does the image run without SELinux denials, with the attestation agent,
   `tactiq-stop` and `agentgateway` active, and with the agent write paths
   of #309 in effect?
4. Do PCR 0 to 9 on the board equal the reference of this build?

## Setup

- Board: the Rock 5A reference board `TACTIQ-BENCH-001`, rollback floor 2,
  development bootloader. The bootloader was not written in this run: the
  build produced `u-boot.itb` sha256 `f7e0a56d…` and `idbloader.img`
  sha256 `cd6c6984…`, the same files that were read back from the board in
  `rollback-seen-dev-20261109.md`, so the reference below is built from
  them.
- The change: the `openembedded-core` line of `integration/LAYERS.lock`
  moves from `0f03c732` to `2285da08`. With it linux-yocto 6.18 moves from
  6.18.52 to 6.18.54, OpenSSL from 3.5.8 to 3.5.9, OpenSSH takes four CVE
  patches, gcc and glibc take stable fixes.
- Built in the development tree from branch `oe-core-wrynose-2285da0`
  (main `88c66fd` with this change) and tactiq-os-selinux `f428657`, the
  revision `integration/LAYERS.lock` pins. `scripts/check-layers.sh
  --check` passed on the layer set before the build.
  `TACTIQ_ROLLBACK_INDEX = "2"` in `local.conf`. Image stamp
  `20261111050318`; kernel `6.18.54-yocto-standard-00166-g689a631dc030`;
  root hash
  `625204bffc135ba045e6e3a4317ef33e63744bca6cde91df9330d1bb841f3034`; the
  boot file system sha256
  `40807a94fd4e68d537b904c64fce4d95edadb9dcb9e39a136aa89b01f1f9a62a`, the
  root file system (`.ext4.verity`, 458735616 bytes)
  `78baf8b019ab886160ac4c8290276da2c0111ea37441132b65826f393bc8d68a`.
- Delivery: from slot A, both partitions of slot B written with `dd` and
  read back to the sums above; `rauc status mark-active other`; cold start
  (power pulled).

## Files

| file | what |
| --- | --- |
| `write-and-boot-b.log` | the console from the login on slot A: the write of slot B and its read-back, the switch, the power-off, and the boot of slot B to the login prompt |
| `checks-b.log` | the checks on slot B and `tpm2_pcrread` after the cold start |
| `pcr-match-b.log` | `pcr-match` over that `tpm2_pcrread` |
| `pcr-ref-oecore-20261111.json` | the reference of this build, from `mk-pcr-reference.py` |

Sums of every file are in `../SHA256SUMS`.

## Results

| question | result |
| --- | --- |
| 1 | yes. U-Boot logs `TactiQ: booting slot B`, `dev-fit+ OK` on the configuration and `Rollback index 2, floor 2 ... OK`, then `raise 0`: the floor was not raised, as slot B had not booted this image before. The kernel mounts the root through verity with the root hash above |
| 2 | yes. `uname -r` reads `6.18.54-yocto-standard-00166-g689a631dc030`; `openssl version` reads `OpenSSL 3.5.9 29 Sep 2026` |
| 3 | yes. `getenforce` reads `Enforcing`; 0 SELinux denials in the journal of the boot; `tactiq-agent`, `tactiq-stop` and `agentgateway` active; `ReadWritePaths=/data/tactiq/keys /data/tactiq/counter /data/tactiq/audit`; the agent writes an envelope every 30 seconds with consecutive counter values |
| 4 | yes. `pcr-match`: PCR 0 to 9 equal the slot B values of `pcr-ref-oecore-20261111.json`, no other reference matches. PCR 10 is not in the reference |

## What this shows and what it does not

- The new pin builds an image that boots and runs on the board as the
  previous one did. The OpenSSH and OpenSSL fixes themselves were not
  exercised.
- linux-yocto 6.18.54 does not carry the fix for CVE-2026-98432 (first in
  6.18.56). This change does not close it; the kernel CVE rule of #305
  applies.
- The CVE check of this build does not list CVE-2026-98432 for
  `linux-yocto-6.18.54`. Why was not investigated here.
- `journalctl` reports one journal file of an earlier boot as truncated
  and ignores it. Not investigated here.
- One board, one boot of the new image. The release image was not built.
