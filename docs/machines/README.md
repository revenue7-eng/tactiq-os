# Per-platform status

Canonical source for per-platform state. `THREAT_MODEL.md`,
`BOOT_CHAIN.md` and `RELEASE_INTEGRITY.md` refer here for anything that
varies between MACHINE configurations.

A cell holds a fact and the file it can be checked against, or
`not established`. A row changes when a measurement or a tree change
makes it change. Intent does not belong in this table.

## Machines in the tree

| MACHINE | Config | Released | Notes |
|---|---|---|---|
| `tactiq-qemu-x86` | `conf/machine/tactiq-qemu-x86.conf` | no | Kernel pinned `6.6%` in the machine config. |
| `tactiq-generic-arm64` | `conf/machine/tactiq-generic-arm64.conf` | no | Template for ARM64 boards. Kernel pinned `6.6%` in the machine config. |
| `tactiq-rock5a` | `meta-tactiq-bsp-rockchip/conf/machine/tactiq-rock5a.conf` | yes | RK3588S. Reference hardware for measurements. |
| `tactiq-rock5a-npu` | `meta-tactiq-bsp-rockchip/conf/machine/tactiq-rock5a-npu.conf` | no | Derives from `tactiq-rock5a`, adds the `npu` override. Never released. |
| `tactiq-rock5t` | `meta-tactiq-bsp-rockchip/conf/machine/tactiq-rock5t.conf` | no | RK3588. Boots on the Rock 5B DTB until a Rock 5T DTS lands. |

## TPM

`MACHINE_FEATURES` carries `tpm2` on `tactiq-generic-arm64`,
`tactiq-rock5a` and `tactiq-rock5t`. The flag builds kernel and
userspace support into the image. It says nothing about a chip being
present.

The kernel config targets a discrete chip over SPI
(`CONFIG_TCG_TIS_SPI`). The agent unit and `agent.yaml` expect
`/dev/tpm0` and `/dev/tpmrm0`. `THREAT_MODEL.md` states that no TPM
device has been exercised on the reference hardware. TPM class per
platform: `not established`.

## OTP fuses

State per platform: `not established`.

## Vendor firmware blobs in the early boot path

RK3588 family (`tactiq-rock5a`, `tactiq-rock5a-npu`, `tactiq-rock5t`),
written to raw sectors before the GPT primary header per the RK3588
BootROM contract, defined in
`meta-tactiq-bsp-rockchip/conf/machine/include/tactiq-rockchip-rk3588.inc`
and placed by `meta-tactiq-bsp-rockchip/files/wic/tactiq-ab-rockchip.wks.in`:

| Blob | Sector | Contents |
|---|---|---|
| `idbloader.img` | 64 | TPL, SPL |
| `u-boot.itb` | 16384 | ARM Trusted Firmware BL31, U-Boot proper |

Both come from `u-boot-rockchip`. The binaries inside `u-boot.itb` are
vendor-supplied and are trusted by delegation. That delegation is stated
in `BOOT_CHAIN.md` § "Vendor firmware blobs".

`tactiq-qemu-x86` and `tactiq-generic-arm64` do not boot from this
path.

## OP-TEE

No TEE is in the boot path. `u-boot-rockchip_2024.07-kwiboo.bb:42`
passes `BL31=` to the FIT and nothing else, and `rkbin_2024.10.bb`
supplies DDR init and BL31 ATF only. BL31 confirms this at runtime:
`selinux-enforcing-boot-prod-20260717.log:119` and both
`selinux-rauc-upstream-enforcing-20260721` runs report no OPTEE from
BL2, and `opteed_fast` fails to initialise. Whether the platform should
carry a TEE at all is an open design question, not a build defect.

## Bring-up status

`tactiq-rock5a` is the board measurements are taken on. See
`measurements/`, and `SUPPLY_CHAIN.md` § "Measurement evidence:
integrity and image scope" for which image profile each measurement
used. No workflow in `.github/workflows/` names a MACHINE, so no
platform has CI coverage that can be checked from this tree. Bring-up
state for `tactiq-generic-arm64`, `tactiq-rock5t` and `tactiq-qemu-x86`:
`not established`.
