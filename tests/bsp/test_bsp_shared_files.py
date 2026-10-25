#!/usr/bin/env python3
"""test_bsp_shared_files.py: the Raspberry Pi BSP layer's copies stay copies.

meta-tactiq-bsp-raspberrypi carries copies of files from
meta-tactiq-bsp-rockchip that both BSP layers need while the common layer
does not hold them yet (meta-tactiq-bsp-raspberrypi/conf/layer.conf). This
fails when a copy differs from its source, so a change to a lockdown
fragment or to the fw_env helper on one platform cannot silently miss the
other.

The Pi default environment (tactiq-boot-fit.env) is not a plain copy: its
partition numbers are shifted by one, because partition 1 on the Pi is the
VideoCore firmware partition. It is compared with the Rockchip file after
that shift and the documented comment changes are undone, so the boot_ab
logic itself cannot drift either.

Run: python3 tests/bsp/test_bsp_shared_files.py
"""
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RK = "meta-tactiq-bsp-rockchip/recipes-bsp"
PI = "meta-tactiq-bsp-raspberrypi/recipes-bsp"

# (Rockchip source as the 2026.10 recipe resolves it, Pi copy)
COPIES = [
    (f"{RK}/u-boot/files/env-lockdown.cfg", f"{PI}/u-boot/files/env-lockdown.cfg"),
    (f"{RK}/u-boot/files/fit-signature.cfg", f"{PI}/u-boot/files/fit-signature.cfg"),
    (f"{RK}/u-boot/files/net-off.cfg", f"{PI}/u-boot/files/net-off.cfg"),
    (f"{RK}/u-boot/files/console-lockdown.cfg", f"{PI}/u-boot/files/console-lockdown.cfg"),
    (f"{RK}/u-boot/u-boot-rockchip-2026.10/boot-ab.cfg", f"{PI}/u-boot/files/boot-ab.cfg"),
    (f"{RK}/u-boot/u-boot-rockchip-2026.10/tools.cfg", f"{PI}/u-boot/files/tools.cfg"),
    (f"{RK}/tactiq-fw-env/files/tactiq-fw-env-setup.sh", f"{PI}/tactiq-fw-env/files/tactiq-fw-env-setup.sh"),
    (f"{RK}/tactiq-fw-env/files/tactiq-fw-env-setup.service", f"{PI}/tactiq-fw-env/files/tactiq-fw-env-setup.service"),
]

ENV_RK = f"{RK}/u-boot/files/tactiq-boot-fit.env"
ENV_PI = f"{PI}/u-boot/files/tactiq-boot-fit.env"

PI_HEADER = (
    "# Raspberry Pi 4 variant of the Rockchip file of the same name. Only the\n"
    "# partition numbers differ: partition 1 is the VideoCore firmware partition,\n"
    "# so boot_a is 0:2 and boot_b is 0:4 (tactiq-ab-rpi.wks.in).\n"
)
PI_FLAGS = (
    "# force is CONFIG_ENV_FLAGS_LIST_STATIC, set in rpi4.cfg and checked by the\n"
    "# recipe. Keep the two in step.\n"
)
RK_FLAGS = (
    "# force is CFG_ENV_FLAGS_LIST_STATIC in include/configs/rock5a-rk3588s.h, added\n"
    "# by patch 0005. Keep the two in step.\n"
)


def read(rel):
    with open(os.path.join(ROOT, rel), "rb") as f:
        return f.read()


def main():
    fails = 0
    for src, dst in COPIES:
        if read(src) != read(dst):
            print(f"FAIL  {dst} differs from {src}")
            fails += 1
        else:
            print(f"OK    {dst}")

    pi = read(ENV_PI).decode()
    rk = read(ENV_RK).decode()
    norm = pi
    for piece in (PI_HEADER, PI_FLAGS):
        if norm.count(piece) != 1:
            print(f"FAIL  {ENV_PI}: expected comment block not found once:\n{piece}")
            fails += 1
    norm = norm.replace(PI_HEADER, "", 1).replace(PI_FLAGS, RK_FLAGS, 1)
    if norm.count("load mmc 0:2 ") != 1 or norm.count("load mmc 0:4 ") != 1:
        print(f"FAIL  {ENV_PI}: expected exactly one load from 0:2 and one from 0:4")
        fails += 1
    norm = norm.replace("load mmc 0:2 ", "load mmc 0:1 ", 1).replace("load mmc 0:4 ", "load mmc 0:3 ", 1)
    if norm != rk:
        print(f"FAIL  {ENV_PI} differs from {ENV_RK} beyond the partition shift")
        fails += 1
    else:
        print(f"OK    {ENV_PI} (partition shift only)")

    if fails:
        print(f"{fails} check(s) failed")
        return 1
    print("BSP copies match their sources.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
