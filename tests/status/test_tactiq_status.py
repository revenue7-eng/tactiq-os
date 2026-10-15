#!/usr/bin/env python3
"""Tests for recipes-core/tactiq-status/files/tactiq-status.

What this guards
----------------

tactiq-status prints what a device reports about itself. Its failure modes are
quiet ones, and each would put a claim on the screen that the device has not
made:

  - "dm-verity" printed for a root that is device-mapper but not a verity
    target, or whose device-mapper name is not the one the command line
    created;
  - IMA reported as on when the loaded policy has no rules (the release image
    ships that way);
  - a PCR composite printed from a partial read;
  - empty envelope files (a published known issue) counted as envelopes
    without saying so;
  - the closing line, which says the screen is not a verification, missing.

The script runs against a synthetic root (TACTIQ_STATUS_ROOT) with stub
tpm2-tools and systemctl on PATH.

Needs: python3, sh, coreutils.
Run: python3 tests/status/test_tactiq_status.py
Against BusyBox, as on the board:
     TACTIQ_STATUS_TEST_SHELL="busybox sh" TACTIQ_STATUS_TEST_PATH=<dir of
     busybox applet links> python3 tests/status/test_tactiq_status.py
"""

import hashlib
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "recipes-core" / "tactiq-status" / "files" / "tactiq-status"

# Command line as recorded on the rc14 release cold boot
# (measurements/rel14-coldboot-20261012-uart.log).
CMD_VERITY = (
    'dm-mod.create="rootfs,,,ro,0 701288 verity 1 /dev/mmcblk0p4 /dev/mmcblk0p4 '
    '4096 4096 87661 87661 sha256 '
    '02a7d9becfbd78e297119d9c531dd93e46b5975982efea1a1293254ca57202c9 '
    '8a7b98d830ac3bf9daa968b9c322bc1e6d9300c632f8f610be59dd67d2c4d797 '
    '1 ignore_zero_blocks" root=/dev/dm-0 ro rootwait rootfstype=ext4 earlycon '
    'panic=5 console=tty1 console=ttyS2,1500000n8 systemd.machine_id=firmware '
    'rauc.slot=B'
)

RELEASE = (
    "TACTIQ_OS_VERSION=2.1.0\n"
    "TACTIQ_OS_CODENAME=hardened-edge\n"
    "TACTIQ_BUILD_MACHINE=tactiq-rock5a\n"
    "TACTIQ_META_TACTIQ_GIT=v2.1.0-rc14\n"
    "TACTIQ_IMAGE_NAME=tactiq-image\n"
    "TACTIQ_RELEASE_DATE=2026-10-12\n"
)

# 10 PCRs x 32 bytes, deterministic.
PCR_BYTES = b"".join(hashlib.sha256(bytes([i])).digest() for i in range(10))

GETCAP = """TPM2_PT_FAMILY_INDICATOR:
  raw: 0x322E3000
  value: "2.0"
TPM2_PT_MANUFACTURER:
  raw: 0x49465800
  value: "IFX"
TPM2_PT_FIRMWARE_VERSION_1:
  raw: 0x70057
TPM2_PT_FIRMWARE_VERSION_2:
  raw: 0x4CEB0002
"""

def envelope(stem, empty=(), missing=()):
    out = []
    for ext in ("attest", "msg", "sig", "tag"):
        if ext in missing:
            continue
        out.append((f"{stem}.{ext}", "" if ext in empty else "x"))
    return out


# Two complete envelopes, one with a zero-length .sig (an older agent after a
# power cut), one without its .tag (a write in progress under the new agent),
# and a leftover .part file.
ENVELOPES = (envelope("135945781248") + envelope("135945781249")
             + envelope("135945781250", empty=("sig",))
             + envelope("135945781251", missing=("tag",))
             + [("135945781252.msg.part", "x")])

FAILURES = []


def check(cond, what):
    if not cond:
        FAILURES.append(what)
        print("FAIL:", what)
    else:
        print("ok:  ", what)


def write(p: Path, text, mode=None):
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        p.write_bytes(text)
    else:
        p.write_text(text)
    if mode is not None:
        p.chmod(mode)


def stub(bindir: Path, name: str, body: str):
    write(bindir / name, "#!/bin/sh\n" + body, 0o755)


def make_root(base: Path, *, cmdline=CMD_VERITY, dm_name="rootfs",
              selinux="1", ima_policy="", ima_count=None, tpm=True,
              envelopes=None):
    r = base / "root"
    write(r / "proc" / "cmdline", cmdline + "\n")
    write(r / "proc" / "device-tree" / "model", b"Radxa ROCK 5A\x00")
    write(r / "etc" / "tactiq-release", RELEASE)
    if dm_name is not None:
        write(r / "sys" / "block" / "dm-0" / "dm" / "name", dm_name + "\n")
    if selinux is not None:
        write(r / "sys" / "fs" / "selinux" / "enforce", selinux)
    if ima_policy is not None:
        write(r / "sys" / "kernel" / "security" / "ima" / "policy", ima_policy)
    if ima_count is not None:
        write(r / "sys" / "kernel" / "security" / "ima" / "runtime_measurements_count",
              f"{ima_count}\n")
    if tpm:
        write(r / "sys" / "class" / "tpm" / "tpm0" / "tpm_version_major", "2\n")
    if envelopes is None:
        envelopes = ENVELOPES
    if envelopes:
        a = r / "data" / "tactiq" / "audit"
        a.mkdir(parents=True, exist_ok=True)
        write(a / "audit.log", "log\n")
        for name, content in envelopes:
            write(a / name, content)
    return r


def make_bin(base: Path, *, tools=True, pcr=PCR_BYTES, agent="active"):
    b = base / "bin"
    b.mkdir(parents=True, exist_ok=True)
    stub(b, "systemctl", f'echo {agent}\n')
    if tools:
        (base / "pcr.bin").write_bytes(pcr)
        (base / "getcap.txt").write_text(GETCAP)
        stub(b, "tpm2_getcap", f'cat "{base}/getcap.txt"\n')
        # tpm2_pcrread -Q -o FILE SEL
        stub(b, "tpm2_pcrread",
             'while [ $# -gt 0 ]; do case "$1" in -o) shift; out="$1";; esac; shift; done\n'
             f'cp "{base}/pcr.bin" "$out"\n')
    return b


def run(root: Path, bindir: Path, *args, env_extra=None):
    # TACTIQ_STATUS_TEST_PATH puts e.g. a directory of busybox applets in front
    # of the system tools, so the script runs against the userland the board
    # has rather than GNU coreutils.
    extra = os.environ.get("TACTIQ_STATUS_TEST_PATH", "")
    env = {
        "PATH": f"{bindir}:{extra + ':' if extra else ''}/usr/bin:/bin",
        "TACTIQ_STATUS_ROOT": str(root),
        "NO_COLOR": "1",
        "LC_ALL": "C.UTF-8",
    }
    if env_extra:
        env.update(env_extra)
    shell = os.environ.get("TACTIQ_STATUS_TEST_SHELL", "sh").split()
    p = subprocess.run([*shell, str(SCRIPT), *args], env=env,
                       capture_output=True, text=True, timeout=30)
    return p.returncode, p.stdout, p.stderr


def field(out: str, label: str) -> str:
    for line in out.splitlines():
        idx = line.find(" " + label + " ")
        if idx >= 0 and line[idx + 1:].startswith(label):
            return line[idx + 1 + len(label):].strip()
    return ""


def scenario(name, **kw):
    tools = kw.pop("tools", True)
    pcr = kw.pop("pcr", PCR_BYTES)
    agent = kw.pop("agent", "active")
    args = kw.pop("args", ())
    env_extra = kw.pop("env_extra", None)
    tmp = Path(tempfile.mkdtemp(prefix=f"tqs-{name}-"))
    root = make_root(tmp, **kw)
    b = make_bin(tmp, tools=tools, pcr=pcr, agent=agent)
    rc, out, err = run(root, b, *args, env_extra=env_extra)
    print(f"\n--- {name} ---\n{out}{err}")
    return rc, out, err


def main():
    if not SCRIPT.is_file():
        print("script not found:", SCRIPT)
        return 1

    # 1. Release-like: verity root, enforcing, IMA with no rules, TPM, agent.
    rc, out, err = scenario("release")
    check(rc == 0, "release: exit 0")
    check(err == "", "release: nothing on stderr")
    check(field(out, "release") == "TactiQ OS v2.1.0-rc14 (tactiq-image)", "release: identity from /etc/tactiq-release")
    check(field(out, "board") == "Radxa ROCK 5A", "release: board from devicetree, NUL stripped")
    check(field(out, "slot") == "B", "release: slot from rauc.slot")
    check(field(out, "root") == 'dm-verity, dm-0 "rootfs" (as booted)', "release: verity root recognised")
    check(field(out, "selinux") == "enforcing", "release: selinux enforcing")
    check(field(out, "ima") == "off (no rules loaded)", "release: empty IMA policy reads as off")
    check(field(out, "tpm") == "present, TPM 2.0, IFX, firmware 7.87.19691.2", "release: tpm manufacturer and firmware decoded")
    d = hashlib.sha256(PCR_BYTES).hexdigest()
    check(field(out, "pcr 0-9") == f"sha256 {d[:12]}...{d[-12:]}", "release: PCR composite is sha256 over 320 bytes")
    check(field(out, "agent") == "active, envelopes: 2 complete, 2 incomplete, 1 .part",
          "release: envelopes counted by stem; empty and untagged ones are incomplete")
    check("this screen is not a verification" in out, "release: closing disclaimer present")
    check("VERIFY-L3 for v2.1.0-rc14" in out, "release: disclaimer names the release")
    for bad in ("verified", "secure", "trusted"):
        check(bad not in out.lower().replace("not a verification", ""), f"release: screen never says '{bad}'")
    check("\033[" not in out, "NO_COLOR: no escape sequences")

    # 2. Development-like: IMA policy with rules and ima_appraise on cmdline.
    pol = "measure func=FILE_CHECK\nmeasure func=BPRM_CHECK\nappraise func=BPRM_CHECK\n"
    rc, out, _ = scenario("dev", cmdline=CMD_VERITY + " ima_appraise=enforce",
                          ima_policy=pol, ima_count=1234)
    check(field(out, "ima") == "policy: measure 2, appraise 1, 1234 entries measured, ima_appraise=enforce",
          "dev: IMA rules counted")

    # 3. Root without device-mapper.
    rc, out, _ = scenario("nodm", cmdline="root=/dev/mmcblk0p2 rw rauc.slot=A")
    check(field(out, "root") == "/dev/mmcblk0p2, no device-mapper", "nodm: plain root reported as such")

    # 4. Device-mapper root whose name differs from the one the cmdline created.
    rc, out, _ = scenario("dmname", dm_name="other")
    check(field(out, "root") == 'device-mapper dm-0 "other", target type not established',
          "dmname: name mismatch is not called verity")

    # 5. Device-mapper root created with a linear target, not verity.
    lin = 'dm-mod.create="rootfs,,,ro,0 701288 linear /dev/mmcblk0p4 0" root=/dev/dm-0 rauc.slot=A'
    rc, out, _ = scenario("linear", cmdline=lin)
    check(field(out, "root") == 'device-mapper dm-0 "rootfs", target type not established',
          "linear: non-verity target is not called verity")

    # 6. The word verity elsewhere on the cmdline does not count.
    trick = 'dm-mod.create="rootfs,,,ro,0 8 linear /dev/x 0" root=/dev/dm-0 note=verity'
    rc, out, _ = scenario("trick", cmdline=trick)
    check("dm-verity" not in field(out, "root"), "trick: 'verity' outside the table is ignored")

    # 7. No SELinux, no TPM, no tools, no audit directory.
    rc, out, _ = scenario("bare", selinux=None, tpm=False, tools=False, envelopes=(),
                          ima_policy=None, agent="inactive")
    check(rc == 0, "bare: exit 0")
    check(field(out, "selinux") == "disabled or not mounted", "bare: selinux absent")
    check(field(out, "ima") == "no IMA interface", "bare: no IMA interface")
    check(field(out, "tpm") == "not found", "bare: tpm absent")
    check(field(out, "pcr 0-9") == "", "bare: no PCR line without a TPM")
    check(field(out, "agent") == "inactive, envelopes: no audit directory", "bare: agent inactive, no audit dir")

    # 7b. No devicetree model: reported on the line, nothing on stderr.
    tmp = Path(tempfile.mkdtemp(prefix="tqs-nomodel-"))
    root = make_root(tmp)
    (root / "proc" / "device-tree" / "model").unlink()
    rc, out, err = run(root, make_bin(tmp))
    check(field(out, "board") == "unknown: no devicetree model", "nomodel: missing model reported")
    check(err == "", "nomodel: nothing on stderr")

    # 7c. Only complete envelopes: no incomplete or .part note.
    rc, out, _ = scenario("clean", envelopes=envelope("1") + envelope("2") + envelope("3"))
    check(field(out, "agent") == "active, envelopes: 3 complete", "clean: three complete envelopes")

    # 8. Short PCR read is not turned into a composite.
    rc, out, _ = scenario("shortpcr", pcr=PCR_BYTES[:96])
    check(field(out, "pcr 0-9") == "sha256 not readable", "shortpcr: partial read refused")

    # 9. Permissive.
    rc, out, _ = scenario("permissive", selinux="0")
    check(field(out, "selinux") == "permissive", "permissive: reported")

    # 10. --plain: ASCII monogram, no colour even on a terminal-less run.
    rc, out, _ = scenario("plain", args=("--plain",), env_extra={"NO_COLOR": ""})
    check(all(ord(c) < 128 for c in out), "plain: output is ASCII only")
    check("###########." in out, "plain: ASCII monogram")

    # 11. Unicode monogram rows line up: every label starts at the same column.
    rc, out, _ = scenario("align")
    cols = set()
    for lbl in ("release", "board", "slot", "root", "selinux", "ima", "tpm", "pcr 0-9", "agent"):
        for line in out.splitlines():
            i = line.find(" " + lbl + " ")
            if i >= 0:
                cols.add(len(line[:i + 1]))
                break
    check(len(cols) == 1, f"align: labels share one column {sorted(cols)}")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s)")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
