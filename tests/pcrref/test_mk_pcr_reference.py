#!/usr/bin/env python3
"""Regression test for the bootm path of scripts/mk-pcr-reference.py.

What this guards, and why it exists
-----------------------------------

On the bootm path each A/B slot boots a FIT configuration of its own, and the
devicetree of each configuration is the kernel's tree with the slot's command
line (the dm-verity table included) written into /chosen bootargs. U-Boot's
bootargs variable is empty at bootm, so that /chosen string is the only
command line the kernel gets.

v2.1.0-rc14 was the first release on this path, and its release run showed
two quiet failures: mk-release.sh still called the extlinux model, and the
loose .dtb was compared byte for byte with the default configuration's
devicetree, which on this path can never match. This test builds a loader
and a FIT synthetically and checks that on the bootm path:

  - the loose .dtb is accepted when each slot's devicetree differs from it
    only in /chosen bootargs, and refused when it differs in anything else;
  - a slot devicetree without /chosen bootargs is refused;
  - the loose Image is checked against the kernel of every slot;
  - components.slots records each slot's command line, so mk-rim.py can carry
    it into the RIM in clear.

Needs: python3.
Run: python3 tests/pcrref/test_mk_pcr_reference.py
"""

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True  # importing the RIM test must leave no __pycache__ in tests/rim

REPO = Path(__file__).resolve().parents[2]
GEN = REPO / "scripts" / "mk-pcr-reference.py"

# The FDT writer of the RIM test, reused rather than copied.
_spec = importlib.util.spec_from_file_location("rimtest", REPO / "tests" / "rim" / "test_mk_rim.py")
T = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(T)
fdt, image, s, u32 = T.fdt, T.image, T.s, T.u32

VER = b"U-Boot 2026.10 (Oct 05 2026 - 21:35:33 +0000)"

CMD_A = ('dm-mod.create="rootfs,,,ro,0 8 verity 1 /dev/mmcblk0p2 /dev/mmcblk0p2 4096 4096 1 1 '
         'sha256 aa bb 1 ignore_zero_blocks" root=/dev/dm-0 ro rauc.slot=A')
CMD_B = CMD_A.replace("mmcblk0p2", "mmcblk0p4").replace("rauc.slot=A", "rauc.slot=B")

failures = []
checks = 0


def check(name, ok, detail=""):
    global checks
    checks += 1
    if not ok:
        failures.append(f"{name}: {detail}" if detail else name)


def kernel_tree(extra_chosen=(), model="Radxa ROCK 5A"):
    """The kernel's devicetree: what the build deploys as the loose .dtb."""
    return ([("model", s(model)), ("compatible", s("radxa,rock-5a"))], [
        ("chosen", ([("stdout-path", s("serial2:1500000n8")), *extra_chosen], [])),
        ("memory", ([("device_type", s("memory"))], [])),
    ])


def slot_tree(cmdline, model="Radxa ROCK 5A"):
    """A slot's devicetree: the kernel tree plus /chosen bootargs."""
    return kernel_tree(extra_chosen=[("bootargs", s(cmdline))], model=model)


def make_itb():
    """u-boot.itb: TF-A, U-Boot proper and its control devicetree, as SPL loads
    them, with the default environment the bootm model reads."""
    boot_ab = (b"boot_ab=for s in ${BOOT_ORDER}; do "
               b"if test x${s} = xA; then setenv rauc_slot A; bootm ${kernel_addr_r}#conf-a; fi; "
               b"if test x${s} = xB; then setenv rauc_slot B; bootm ${kernel_addr_r}#conf-b; fi; done")
    uboot = (b"\x00" + VER + b"\x00\x00bootcmd=run boot_ab\x00" + boot_ab + b"\x00"
             b"BOOT_ORDER:sw,BOOT_A_LEFT:dw,BOOT_B_LEFT:dw\x00")
    ctl = fdt(([], []))
    root = ([("description", s("u-boot"))], [
        ("images", ([], [
            ("atf-1", image(b"TF-A" * 32, extra=[("os", s("arm-trusted-firmware"))])),
            ("u-boot", image(uboot, extra=[("os", s("u-boot"))])),
            ("fdt-1", image(ctl, extra=[("type", s("flat_dt"))])),
        ])),
        ("configurations", ([("default", s("config-1"))], [
            ("config-1", ([("firmware", s("atf-1")), ("loadables", s("u-boot")),
                           ("fdt", s("fdt-1"))], []))])),
    ])
    return fdt(root)


def make_fit(dtb_a, dtb_b, kernel=b"KERNEL" * 64, kernel_b=None):
    sig = [("signature-1", ([("algo", s("sha256,rsa2048")), ("key-name-hint", s("release-fit"))], []))]
    kb = kernel if kernel_b is None else kernel_b
    imgs = [("kernel-1", image(kernel, extra=[("load", u32(0x08000000))])),
            ("fdt-a", image(dtb_a)), ("fdt-b", image(dtb_b))]
    kname_b = "kernel-1"
    if kernel_b is not None:
        imgs.append(("kernel-2", image(kb, extra=[("load", u32(0x08000000))])))
        kname_b = "kernel-2"
    root = ([], [
        ("images", ([], imgs)),
        ("configurations", ([("default", s("conf-a"))], [
            ("conf-a", ([("kernel", s("kernel-1")), ("fdt", s("fdt-a"))], sig)),
            ("conf-b", ([("kernel", s(kname_b)), ("fdt", s("fdt-b"))], sig)),
        ])),
    ])
    return fdt(root)


def run(d, fit, loose_dtb=None, loose_image=None):
    (d / "fitImage-rock5a").write_bytes(fit)
    (d / "u-boot-rock5a.itb").write_bytes(make_itb())
    (d / "idbloader-rock5a.img").write_bytes(b"SPL\x00" + VER + b"\x00")
    args = [sys.executable, str(GEN), "--fit", str(d / "fitImage-rock5a"),
            "--uboot", str(d / "u-boot-rock5a.itb"),
            "--idbloader", str(d / "idbloader-rock5a.img"), "--out", str(d / "ref.json")]
    if loose_dtb is not None:
        (d / "loose.dtb").write_bytes(loose_dtb)
        args += ["--dtb", str(d / "loose.dtb")]
    if loose_image is not None:
        (d / "Image").write_bytes(loose_image)
        args += ["--image", str(d / "Image")]
    out = d / "ref.json"
    out.unlink(missing_ok=True)
    return subprocess.run(args, capture_output=True, text=True), out


def main():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        loose = fdt(kernel_tree())
        good_fit = make_fit(fdt(slot_tree(CMD_A)), fdt(slot_tree(CMD_B)))

        r, out = run(d, good_fit, loose_dtb=loose, loose_image=b"KERNEL" * 64)
        check("good: exits 0", r.returncode == 0, r.stderr.strip())
        if r.returncode == 0:
            ref = json.loads(out.read_text())
            check("good: format 2, bootm", ref.get("format") == "tactiq-pcr-reference/2"
                  and ref.get("boot_path") == "bootm", str(ref.get("format")))
            sl = ref["components"]["slots"]
            check("good: both slots", sorted(sl) == ["A", "B"], str(sorted(sl)))
            check("good: command line of slot A recorded", sl.get("A", {}).get("cmdline") == CMD_A)
            check("good: command line of slot B recorded", sl.get("B", {}).get("cmdline") == CMD_B)
            check("good: PCR 1 per slot (2026.10 measures the devicetree there)",
                  isinstance(ref["pcr"]["1"], dict) and sorted(ref["pcr"]["1"]) == ["A", "B"])

        r, _ = run(d, good_fit)
        check("no loose files: exits 0", r.returncode == 0, r.stderr.strip())

        r, _ = run(d, good_fit, loose_dtb=fdt(kernel_tree(extra_chosen=[("bootargs", s("console=ttyS2"))])))
        check("loose DTB with its own bootargs: still only bootargs differ", r.returncode == 0, r.stderr.strip())

        r, out = run(d, good_fit, loose_dtb=fdt(kernel_tree(model="Something else")))
        check("loose DTB differing outside /chosen bootargs: refused",
              r.returncode != 0 and "differs from the loose DTB" in r.stderr, r.stderr.strip())
        check("loose DTB differing outside /chosen bootargs: writes nothing", not out.exists())

        bad_b = make_fit(fdt(slot_tree(CMD_A)), fdt(slot_tree(CMD_B, model="Tampered")))
        r, _ = run(d, bad_b, loose_dtb=loose)
        check("only slot B differs: refused and names slot B",
              r.returncode != 0 and "slot B" in r.stderr, r.stderr.strip())

        no_args = make_fit(fdt(slot_tree(CMD_A)), fdt(kernel_tree()))
        r, out = run(d, no_args)
        check("slot devicetree without /chosen bootargs: refused",
              r.returncode != 0 and "has no /chosen bootargs" in r.stderr, r.stderr.strip())
        check("slot devicetree without /chosen bootargs: writes nothing", not out.exists())

        two_kernels = make_fit(fdt(slot_tree(CMD_A)), fdt(slot_tree(CMD_B)), kernel_b=b"OTHER" * 64)
        r, _ = run(d, two_kernels, loose_image=b"KERNEL" * 64)
        check("loose Image differs from slot B's kernel: refused",
              r.returncode != 0 and "kernel of configuration conf-b (slot B)" in r.stderr, r.stderr.strip())

        r, _ = run(d, good_fit, loose_image=b"WRONG" * 64)
        check("loose Image differs from the default kernel: refused",
              r.returncode != 0 and "loose Image differs" in r.stderr, r.stderr.strip())

    print(f"{checks} checks, {len(failures)} failed")
    for f in failures:
        print(f"FAIL {f}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
