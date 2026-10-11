#!/usr/bin/env python3
"""mk-pcr-reference.py: expected SHA-256 PCR values for a TactiQ OS FIT boot,
derived from release artefacts without the device.

Two boot paths are modelled.

bootm (default, no --extlinux): the loader's boot_ab loads the signed FIT and
runs bootm with an explicit configuration per slot. Slots and configurations
are read from the default environment compiled into u-boot.itb, which is what
the loader executes (CONFIG_ENV_WRITEABLE_LIST imports only BOOT_ORDER and the
BOOT_x_LEFT counters from storage). The kernel command line lives in /chosen of
each configuration's devicetree, so it is covered by the devicetree digest
(PCR 0 or PCR 1, see below); U-Boot's bootargs variable is empty and its
measurement in PCR 1 is the same for every
slot. The script refuses a boot_ab that calls sysboot or sets bootargs, a
bootcmd other than `run boot_ab`, and a compiled-in writable list that admits
bootargs, bootcmd, boot_ab or preboot: each would let an unsigned command line
reach the kernel (SF-001).

extlinux (--extlinux and --boot-env): the older path, sysboot of extlinux.conf.
Inputs are fitImage and extlinux.conf from the boot partition, u-boot.itb, and
the U-Boot environment file that sets rauc_slot / rauc_part per slot
(tactiq-boot.env). Kept to recompute references of loaders built before bootm.

Each PCR is extended in boot order, E(p, d) = sha256(p || d) from p0 = 32
zero bytes, and closed with s = sha256(ffffffff) for PCR 0-7.

SPL, the root of the chain, measures every image it loads from u-boot.itb
after checking its hash, in the order SPL loads them (firmware, then each
loadable, with the U-Boot devicetree right after U-Boot):
  PCR 0  S-CRTM version, then each firmware image (TF-A, OP-TEE)
  PCR 4  U-Boot proper
  PCR 6  U-Boot control devicetree (carries the FIT verification key)
U-Boot proper then measures:
  PCR 0  S-CRTM version, then the kernel devicetree    bootm: one value per slot
  PCR 1  bootargs variable, NUL-terminated               bootm: empty, one value
The kernel devicetree goes to PCR 0 in U-Boot 2024.07 and to PCR 1 (before
bootargs) in 2026.10 (boot/bootm.c, EV_TABLE_OF_DEVICES). FDT_PCR maps each
U-Boot version this script knows to that PCR; any other version is refused
until its boot/bootm.c has been read.
                                                         extlinux: one per slot
  PCR 8  kernel                                         bootm: per configuration
  PCR 9  "initrd" NUL                                   no initrd
--no-spl-measure computes the values for a loader whose SPL measures nothing.

kernel and fdt are the payloads of the FIT configuration each slot boots (the
default configuration on the extlinux path). Their digests are checked against the hash nodes inside the FIT, and against loose
Image / .dtb files when those are given. Any mismatch aborts.

No third-party modules and no u-boot-tools: the FIT is parsed here so that a
reader holding only the published files can rerun the computation. The output
names inputs by basename only and carries no build-host paths.
"""

import argparse
import hashlib
import json
import os
import re
import struct
import sys

P0 = bytes(32)
SEP = hashlib.sha256(b"\xff\xff\xff\xff").digest()


def die(msg):
    print(f"mk-pcr-reference: error: {msg}", file=sys.stderr)
    sys.exit(1)


def sha(b):
    return hashlib.sha256(b).digest()


def ext(pcr, digest):
    return hashlib.sha256(pcr + digest).digest()


def hx(b):
    return b.hex().upper()


def read(path):
    with open(path, "rb") as f:
        return f.read()


# --- minimal flattened device tree parser (FIT is an FDT) -------------------

def parse_fdt(buf):
    if len(buf) < 40:
        die("file too short to be an FDT")
    (magic, totalsize, off_struct, off_strings, _rsv, _ver, _lcv, _cpu,
     size_strings, size_struct) = struct.unpack_from(">10I", buf, 0)
    if magic != 0xD00DFEED:
        die("not an FDT/FIT (bad magic)")
    strings = buf[off_strings:off_strings + size_strings]

    def prop_name(off):
        return strings[off:strings.index(b"\0", off)].decode()

    holder = {"props": {}, "nodes": {}}
    stack = [holder]
    p, end = off_struct, off_struct + size_struct
    while p < end:
        (tok,) = struct.unpack_from(">I", buf, p)
        p += 4
        if tok == 1:  # BEGIN_NODE
            e = buf.index(b"\0", p)
            name = buf[p:e].decode()
            p = (e + 4) & ~3
            node = {"props": {}, "nodes": {}}
            stack[-1]["nodes"][name] = node
            stack.append(node)
        elif tok == 2:  # END_NODE
            stack.pop()
        elif tok == 3:  # PROP
            ln, nameoff = struct.unpack_from(">II", buf, p)
            p += 8
            stack[-1]["props"][prop_name(nameoff)] = buf[p:p + ln]
            p = (p + ln + 3) & ~3
        elif tok == 4:  # NOP
            continue
        elif tok == 9:  # END
            break
        else:
            die(f"bad FDT token {tok} at offset {p - 4}")
    if "" not in holder["nodes"]:
        die("FDT has no root node")
    return holder["nodes"][""], totalsize


def pstr(node, key):
    if key not in node["props"]:
        return None
    return node["props"][key].rstrip(b"\0").decode()


def pu32(node, key):
    return struct.unpack(">I", node["props"][key])[0]


def fit_payload(buf, totalsize, img, label):
    pr = img["props"]
    if "data" in pr:
        data = pr["data"]
    elif "data-size" in pr:
        size = pu32(img, "data-size")
        if "data-position" in pr:
            off = pu32(img, "data-position")
        elif "data-offset" in pr:
            off = ((totalsize + 3) & ~3) + pu32(img, "data-offset")
        else:
            die(f"{label}: external data without a position")
        data = buf[off:off + size]
        if len(data) != size:
            die(f"{label}: external data truncated")
    else:
        die(f"{label}: image node has no data")
    hashes = [n for k, n in img["nodes"].items() if k.startswith("hash")]
    sha_nodes = [n for n in hashes if pstr(n, "algo") == "sha256"]
    if not sha_nodes:
        die(f"{label}: no sha256 hash node in the FIT")
    digest = sha(data)
    for n in sha_nodes:
        if n["props"]["value"] != digest:
            die(f"{label}: payload does not match its own hash node")
    return data, digest


def read_fit(path, want=None):
    buf = read(path)
    root, totalsize = parse_fdt(buf)
    images = root["nodes"].get("images")
    confs = root["nodes"].get("configurations")
    if images is None or confs is None:
        die("FIT has no /images or /configurations")
    default = pstr(confs, "default")
    if want is not None:
        if want not in confs["nodes"]:
            die(f"FIT has no configuration {want}")
        default = want
    if default is None or default not in confs["nodes"]:
        die("FIT has no usable default configuration")
    conf = confs["nodes"][default]
    kname, fname = pstr(conf, "kernel"), pstr(conf, "fdt")
    if kname is None or fname is None:
        die(f"configuration {default} lacks kernel or fdt")
    kernel, kdig = fit_payload(buf, totalsize, images["nodes"][kname], kname)
    _fdt, fdig = fit_payload(buf, totalsize, images["nodes"][fname], fname)
    sigs = [n for k, n in conf["nodes"].items() if k.startswith("signature")]
    hints = sorted({pstr(n, "key-name-hint") or "" for n in sigs})
    return {
        "configuration": default,
        "configurations": sorted(confs["nodes"]),
        "kernel_sha256": kdig,
        "fdt_sha256": fdig,
        "key_name_hint": hints,
        "load": pu32(images["nodes"][kname], "load")
        if "load" in images["nodes"][kname]["props"] else None,
    }


# --- SPL measurements from u-boot.itb --------------------------------------

def spl_pcr_for(img):
    """PCR SPL extends for an image node, or None (see spl-measure.c)."""
    typ = (pstr(img, "type") or "").lower()
    osn = (pstr(img, "os") or "").lower()
    if typ == "flat_dt":
        return 6
    if osn == "u-boot":
        return 4
    if osn in ("arm-trusted-firmware", "tee"):
        return 0
    return None


def spl_events(path):
    """Replay the load order of common/spl/spl_fit.c:spl_load_simple_fit."""
    buf = read(path)
    root, totalsize = parse_fdt(buf)
    images = root["nodes"].get("images")
    confs = root["nodes"].get("configurations")
    if images is None or confs is None:
        die("u-boot.itb has no /images or /configurations")
    default = pstr(confs, "default")
    if default is None or default not in confs["nodes"]:
        die("u-boot.itb has no usable default configuration")
    conf = confs["nodes"][default]

    def names(prop):
        raw = conf["props"].get(prop, b"")
        return [x.decode() for x in raw.split(b"\0") if x]

    firmware, loadables, fdts = names("firmware"), names("loadables"), names("fdt")
    order, index = [], 0
    if firmware:
        first = firmware[0]
    elif loadables:
        first, index = loadables[0], 1
    else:
        die("u-boot.itb default configuration names no firmware or loadables")

    def takes_dt(name):
        return (pstr(images["nodes"][name], "os") or "").lower() == "u-boot"

    def load(name):
        order.append(name)
        if takes_dt(name):
            if not fdts:
                die("U-Boot loaded but no fdt in the default configuration")
            order.append(fdts[0])

    load(first)
    for name in loadables[index:]:
        if name != first:
            load(name)

    events = []
    for name in order:
        img = images["nodes"].get(name)
        if img is None:
            die(f"u-boot.itb configuration names a missing image {name}")
        pcr = spl_pcr_for(img)
        if pcr is None:
            die(f"u-boot.itb image {name} has no PCR assignment; SPL would "
                "load it unmeasured")
        _data, digest = fit_payload(buf, totalsize, img, name)
        events.append({"image": name, "pcr": pcr, "sha256": digest})
    return default, events


# --- other inputs -----------------------------------------------------------

VER_RE = re.compile(
    rb"U-Boot 20\d\d\.\d\d[^\x00\n]*?"
    rb"\([A-Z][a-z]{2} [ 0-9]\d \d{4} - \d\d:\d\d:\d\d [+-]\d{4}\)"
    rb"[^\x00\n]*(?=\x00)")


def uboot_version(path):
    found = sorted(set(VER_RE.findall(read(path))))
    if len(found) != 1:
        die(f"expected one U-Boot version string in {os.path.basename(path)}, "
            f"found {len(found)}: {[f.decode(errors='replace') for f in found]}")
    return found[0]


def read_extlinux(path):
    kernel = fdt = append = None
    count = 0
    for line in read(path).decode().splitlines():
        s = line.strip()
        word, _, rest = s.partition(" ")
        rest = rest.lstrip()
        if word == "APPEND":
            append, count = rest, count + 1
        elif word == "KERNEL":
            kernel = rest
        elif word == "FDT":
            fdt = rest
    if count != 1:
        die(f"expected exactly one APPEND line, found {count}")
    if kernel is None or fdt != kernel:
        die(f"FDT ({fdt}) is not the FIT named by KERNEL ({kernel}): "
            "U-Boot would take a DTB from outside the signed configuration")
    return kernel, append


BOOTAB_RE = re.compile(rb"boot_ab=([^\0]*)\0")
SLOT_RE = re.compile(
    r"setenv rauc_slot (\w+);.*?"
    r"bootm \$\{kernel_addr_r\}#([A-Za-z0-9_.,+-]+)")


def read_boot_ab(path):
    """Slot -> FIT configuration from boot_ab in the loader's default env."""
    found = sorted(set(BOOTAB_RE.findall(read(path))))
    if len(found) != 1:
        die(f"expected one boot_ab in {os.path.basename(path)}, found {len(found)}")
    text = found[0].decode()
    if "sysboot" in text:
        die("boot_ab calls sysboot: extlinux APPEND would override the signed "
            "command line (SF-001); use --extlinux/--boot-env for such a loader")
    if "bootargs" in text:
        die("boot_ab sets bootargs: the kernel command line would not come "
            "from the signed configuration (SF-001)")
    pairs = SLOT_RE.findall(text)
    slots = dict(pairs)
    if len(slots) != len(pairs) or not slots:
        die("rauc_slot / bootm configuration pairs missing or ambiguous in boot_ab")
    return slots, sha(found[0]).hex()


BOOTCMD_RE = re.compile(rb"\0bootcmd=([^\0]*)\0")
# PCR that U-Boot proper's bootm measures the kernel devicetree into, by
# version (boot/bootm.c). 2024.07: tcg2_measure_data(..., 0, ...,
# EV_TABLE_OF_DEVICES). 2026.10: the same event into PCR 1. Observed on the
# reference board on 2026-10-08 for 2026.10 by the event log.
FDT_PCR = {(2024, 7): 0, (2026, 10): 1}

FORBIDDEN_WRITABLE = ("bootargs", "bootcmd", "boot_ab", "preboot")


def read_env_lockdown(path):
    """Check that the loader runs boot_ab and imports only safe variables.

    The bootm model holds only if bootcmd is `run boot_ab` and the
    compiled-in CONFIG_ENV_WRITEABLE_LIST lets nothing that shapes the boot
    (bootargs, bootcmd, boot_ab, preboot) come from stored environment.
    """
    buf = read(path)
    cmds = sorted(set(BOOTCMD_RE.findall(buf)))
    if cmds != [b"run boot_ab"]:
        die(f"bootcmd in {os.path.basename(path)} is {cmds}, expected "
            "['run boot_ab']")
    lists = set()
    for chunk in buf.split(b"\0"):
        if b"BOOT_ORDER:" in chunk and not chunk.startswith(b".flags="):
            try:
                lists.add(chunk.decode("ascii"))
            except UnicodeDecodeError:
                continue
    if len(lists) != 1:
        die(f"expected one compiled-in env flags list naming BOOT_ORDER in "
            f"{os.path.basename(path)}, found {len(lists)}: without it "
            "CONFIG_ENV_WRITEABLE_LIST cannot be confirmed")
    flags = lists.pop()
    writable = []
    for entry in filter(None, flags.split(",")):
        name, sep, attr = entry.rpartition(":")
        if not sep or not name:
            die(f"cannot parse env flags entry {entry!r} in {flags!r}")
        if "w" in attr:
            writable.append(name)
    bad = [n for n in writable if n in FORBIDDEN_WRITABLE]
    if bad:
        die(f"stored environment may set {bad}: the command line would not "
            "come from the signed configuration (SF-001)")
    if "BOOT_ORDER" not in writable:
        die(f"BOOT_ORDER is not writable in {flags!r}: RAUC could not "
            "switch slots, this is not the expected loader")
    return flags, sorted(writable)


def one_or_per_slot(d):
    vals = set(d.values())
    return next(iter(vals)) if len(vals) == 1 else d


def read_slots(path):
    pairs = re.findall(r"setenv rauc_slot (\w+); setenv rauc_part (\w+);",
                       read(path).decode())
    slots = dict(pairs)
    if len(slots) != len(pairs) or not slots:
        die("rauc_slot / rauc_part pairs missing or ambiguous in the boot env")
    return slots


def cmdline_for(append, slot, part):
    c = append.replace("${rauc_part}", part).replace("${rauc_slot}", slot)
    if "${" in c:
        die(f"unexpanded variable left in cmdline for slot {slot}: {c}")
    return c


# --- main -------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--fit", required=True)
    ap.add_argument("--extlinux", help="extlinux path only (sysboot loaders)")
    ap.add_argument("--uboot", required=True, help="u-boot.itb")
    ap.add_argument("--boot-env", help="tactiq-boot.env, extlinux path only")
    ap.add_argument("--image", help="loose kernel Image to cross-check")
    ap.add_argument("--dtb", help="loose DTB to cross-check")
    ap.add_argument("--require-key", help="fail unless the FIT is signed with this key-name-hint")
    ap.add_argument("--idbloader", help="idbloader.img; its SPL version string must match u-boot.itb")
    ap.add_argument("--no-spl-measure", action="store_true",
                    help="loader whose SPL measures nothing (before SPL measured boot)")
    ap.add_argument("--check", action="append", default=[],
                    metavar="PCR[:SLOT]=HEX",
                    help="compare a computed value, e.g. 8=BAA2... or 1:B=BBE1...")
    ap.add_argument("--out", help="write JSON here instead of stdout")
    a = ap.parse_args()

    fit = read_fit(a.fit)
    if a.image and sha(read(a.image)) != fit["kernel_sha256"]:
        die("loose Image differs from the kernel inside the FIT")
    if a.dtb and sha(read(a.dtb)) != fit["fdt_sha256"]:
        die("loose DTB differs from the FDT inside the FIT")
    if a.require_key and fit["key_name_hint"] != [a.require_key]:
        die(f"FIT signed with {fit['key_name_hint']}, required {a.require_key}")

    if bool(a.extlinux) != bool(a.boot_env):
        die("--extlinux and --boot-env go together (extlinux path); "
            "give neither for the bootm path")
    mode = "extlinux" if a.extlinux else "bootm"

    ver = uboot_version(a.uboot)
    if a.idbloader:
        spl_ver = uboot_version(a.idbloader)
        if spl_ver != ver:
            die(f"SPL version {spl_ver!r} differs from U-Boot version {ver!r}")

    crtm = sha(ver + b"\0")
    m = re.match(rb"U-Boot (\d{4})\.(\d{2})", ver)
    fdt_pcr = FDT_PCR.get((int(m.group(1)), int(m.group(2)))) if m else None
    if fdt_pcr is None:
        die(f"U-Boot version {ver!r} is not in FDT_PCR: read boot/bootm.c of "
            "that version for the PCR it measures the kernel devicetree into")
    spl_conf, spl = None, []
    spl_chain = {i: [] for i in range(0, 10)}
    if not a.no_spl_measure:
        spl_conf, spl = spl_events(a.uboot)
        spl_chain[0].append(crtm)
        for e in spl:
            spl_chain[e["pcr"]].append(e["sha256"])

    def value(digests):
        v = P0
        for d in digests:
            v = ext(v, d)
        return v

    def pcrs_for(kernel, fdt):
        # U-Boot proper, boot/bootm.c: S-CRTM, kernel, initrd, devicetree,
        # command line, then separators on PCR 0-7.
        chain = {i: list(spl_chain[i]) for i in range(0, 10)}
        chain[0].append(crtm)
        chain[8].append(kernel)
        chain[9].append(sha(b"initrd\0"))
        chain[fdt_pcr].append(fdt)
        out = {}
        for i in range(0, 10):
            if i == 1:
                continue
            tail = [SEP] if i < 8 else []
            out[str(i)] = hx(value(chain[i] + tail))
        return out

    base = os.path.basename
    spl_list = [{"image": e["image"], "pcr": e["pcr"], "sha256": e["sha256"].hex()}
                for e in spl]
    spl_assumption = (
        "SPL measures the images of u-boot.itb and is itself unmeasured: "
        "it is the root of the measurement chain"
        if not a.no_spl_measure else
        "SPL measures nothing (--no-spl-measure): U-Boot proper is the "
        "root of the measurement chain")
    tail_args = "{}{}".format(
        f" --idbloader {base(a.idbloader)}" if a.idbloader else "",
        " --no-spl-measure" if a.no_spl_measure else "")

    if mode == "bootm":
        slots, bootab_sha = read_boot_ab(a.uboot)
        env_flags, env_writable = read_env_lockdown(a.uboot)
        per = {}
        confs = {}
        for s_, cname in sorted(slots.items()):
            f = fit if cname == fit["configuration"] else read_fit(a.fit, cname)
            confs[s_] = f
            per[s_] = pcrs_for(f["kernel_sha256"], f["fdt_sha256"])
        pcr = {}
        for i in range(0, 10):
            if i == 1:
                continue
            pcr[str(i)] = one_or_per_slot({s_: v[str(i)] for s_, v in per.items()})
        pcr["1"] = one_or_per_slot({
            s_: hx(value(([f["fdt_sha256"]] if fdt_pcr == 1 else [])
                         + [sha(b"\0"), SEP]))
            for s_, f in confs.items()})
        doc = {
            "format": "tactiq-pcr-reference/2",
            "bank": "sha256",
            "boot_path": "bootm",
            "assumptions": [
                "U-Boot runs boot_ab from the default environment compiled into "
                "u-boot.itb (bootcmd is run boot_ab); only the variables under "
                "components.env_writable are imported from storage "
                "(CONFIG_ENV_WRITEABLE_LIST), checked to exclude bootargs, "
                "bootcmd, boot_ab and preboot",
                "the values hold only while the loader itself is the one built: "
                "SPL is neither measured nor verified by the boot ROM until the "
                "SoC OTP key is fused, and a replaced SPL can extend these same "
                "values",
                "bootargs is empty at bootm; a PCR 1 other than the one given "
                "means a command line outside the signed configuration reached "
                "U-Boot",
                "the kernel command line, including the dm-verity root hash, is "
                "in /chosen of each configuration's devicetree and is covered "
                f"by the devicetree digest in PCR {fdt_pcr}",
                "the boot partition of each slot carries the fitImage named "
                "under inputs",
                "no initrd is loaded",
                spl_assumption,
            ],
            "inputs": {
                base(a.fit): sha(read(a.fit)).hex(),
                base(a.uboot): sha(read(a.uboot)).hex(),
            },
            "components": {
                "uboot_version": ver.decode(),
                "boot_ab_sha256": bootab_sha,
                "env_flags_list": env_flags,
                "env_writable": env_writable,
                "fit_default_configuration": fit["configuration"],
                "fit_configurations": fit["configurations"],
                "fit_key_name_hint": fit["key_name_hint"],
                "slots": {
                    s_: {
                        "fit_configuration": f["configuration"],
                        "kernel_sha256": f["kernel_sha256"].hex(),
                        "kernel_load": None if f["load"] is None
                        else f"0x{f['load']:08x}",
                        "fdt_sha256": f["fdt_sha256"].hex(),
                    } for s_, f in confs.items()},
                "bootargs": "",
                "kernel_devicetree_pcr": fdt_pcr,
                "spl_configuration": spl_conf,
                "spl_measurements": spl_list,
            },
            "pcr": pcr,
            "recompute": "python3 mk-pcr-reference.py --fit {} --uboot {}{}".format(
                base(a.fit), base(a.uboot), tail_args),
        }
    else:
        kpath, append = read_extlinux(a.extlinux)
        slots = read_slots(a.boot_env)
        pcr = pcrs_for(fit["kernel_sha256"], fit["fdt_sha256"])
        cmdlines = {s_: cmdline_for(append, s_, p_) for s_, p_ in sorted(slots.items())}
        pcr["1"] = {s_: hx(value(([fit["fdt_sha256"]] if fdt_pcr == 1 else [])
                                 + [sha(c.encode() + b"\0"), SEP]))
                    for s_, c in cmdlines.items()}
        doc = {
            "format": "tactiq-pcr-reference/1",
            "bank": "sha256",
            "assumptions": [
                "U-Boot runs with the default environment of this release; a saved "
                "environment with a different boot_ab changes PCR 1",
                "the boot partition of each slot carries the fitImage and "
                "extlinux.conf named under inputs",
                "no initrd is loaded",
                spl_assumption,
            ],
            "inputs": {
                base(a.fit): sha(read(a.fit)).hex(),
                base(a.extlinux): sha(read(a.extlinux)).hex(),
                base(a.uboot): sha(read(a.uboot)).hex(),
                base(a.boot_env): sha(read(a.boot_env)).hex(),
            },
            "components": {
                "uboot_version": ver.decode(),
                "fit_configuration": fit["configuration"],
                "fit_configurations": fit["configurations"],
                "fit_key_name_hint": fit["key_name_hint"],
                "extlinux_kernel": kpath,
                "kernel_sha256": fit["kernel_sha256"].hex(),
                "kernel_load": None if fit["load"] is None else f"0x{fit['load']:08x}",
                "fdt_sha256": fit["fdt_sha256"].hex(),
                "cmdline": cmdlines,
                "spl_configuration": spl_conf,
                "spl_measurements": spl_list,
            },
            "pcr": pcr,
            "recompute": "python3 mk-pcr-reference.py --fit {} --extlinux {} "
                         "--uboot {} --boot-env {}{}".format(
                             base(a.fit), base(a.extlinux), base(a.uboot),
                             base(a.boot_env), tail_args),
        }

    text = json.dumps(doc, indent=2, sort_keys=True) + "\n"
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        sys.stdout.write(text)

    bad = 0
    for c in a.check:
        key, _, want = c.partition("=")
        idx, _, slot = key.partition(":")
        got = pcr.get(idx)
        if isinstance(got, dict):
            got = got.get(slot)
        ok = got is not None and got == want.strip().upper()
        bad += not ok
        print(f"check PCR {key}: {'OK' if ok else 'FAIL'}"
              + ("" if ok else f" (computed {got})"), file=sys.stderr)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
