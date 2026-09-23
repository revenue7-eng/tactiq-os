#!/usr/bin/env python3
"""Regression test for scripts/mk-rim.py.

What this guards, and why it exists
-----------------------------------

The RIM is the signed statement a verifier matches a device against. Its
failure modes are quiet ones: a key fingerprint computed from the wrong bytes
still looks like a fingerprint, a PCR value in the wrong case still looks like
a digest, a FIT that is not the one the PCR reference was computed from still
yields a RIM. Each of these produces a manifest that reads as complete and
states more than was checked.

This test builds every input synthetically (a FIT with sha256 hash nodes, a
u-boot.itb whose control device tree carries the verification key, a PCR
reference, a RAUC keyring, an identity file) and checks two things:

  - the fingerprints in the RIM agree with the ones openssl computes on its
    own from the same keys, the output is byte-identical across runs, and it
    validates against schemas/rim-v1.json;
  - every consistency gate refuses what it is there to refuse.

Needs: python3, openssl, jsonschema (pip install jsonschema).
Run: python3 tests/rim/test_mk_rim.py
"""

import copy
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GEN = REPO / "scripts" / "mk-rim.py"
SCHEMA = REPO / "schemas" / "rim-v1.json"

VER_A = b"U-Boot 2025.10 (Sep 22 2026 - 16:10:55 +0000)"
VER_B = b"U-Boot 2025.10 (Sep 23 2026 - 09:00:00 +0000)"

failures = []
checks = 0


def check(name, ok, detail=""):
    global checks
    checks += 1
    if not ok:
        failures.append(f"{name}: {detail}" if detail else name)


def sha(b):
    return hashlib.sha256(b).digest()


# --- a minimal FDT writer ---------------------------------------------------
# A node is (props, children): props an ordered list of (name, bytes),
# children an ordered list of (name, node).

def s(v):
    return v.encode() + b"\0"


def u32(v):
    return struct.pack(">I", v)


def fdt(root):
    strings, offs = bytearray(), {}
    body = bytearray()

    def name_off(n):
        if n not in offs:
            offs[n] = len(strings)
            strings.extend(n.encode() + b"\0")
        return offs[n]

    def pad():
        while len(body) % 4:
            body.append(0)

    def emit(name, node):
        props, children = node
        body.extend(u32(1))
        body.extend(name.encode() + b"\0")
        pad()
        for pn, pv in props:
            body.extend(u32(3) + u32(len(pv)) + u32(name_off(pn)))
            body.extend(pv)
            pad()
        for cn, cnode in children:
            emit(cn, cnode)
        body.extend(u32(2))

    emit("", root)
    body.extend(u32(9))
    off_rsv = 40
    off_struct = off_rsv + 16
    off_strings = off_struct + len(body)
    total = off_strings + len(strings)
    hdr = struct.pack(">10I", 0xD00DFEED, total, off_struct, off_strings, off_rsv,
                      17, 16, 0, len(strings), len(body))
    return hdr + bytes(16) + bytes(body) + bytes(strings)


def image(data, extra=(), hashed=True):
    kids = [("hash-1", ([("algo", s("sha256")), ("value", sha(data))], []))] if hashed else []
    return ([("data", data), *extra], kids)


# --- fixtures ---------------------------------------------------------------

def openssl(*args, data=None):
    r = subprocess.run(["openssl", *args], input=data, capture_output=True)
    if r.returncode:
        raise SystemExit(f"fixture: openssl {' '.join(args)} failed: {r.stderr.decode()}")
    return r.stdout


def rsa_key(d, name):
    key = d / f"{name}.key.pem"
    openssl("genrsa", "-out", str(key), "3072")
    mod = openssl("rsa", "-in", str(key), "-noout", "-modulus").decode().strip()
    n = int(mod.split("=", 1)[1], 16)
    spki = openssl("pkey", "-in", str(key), "-pubout", "-outform", "DER")
    return n, 65537, sha(spki).hex()


def cert(d, name, cn):
    key, crt = d / f"{name}.key.pem", d / f"{name}.pem"
    openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key),
            "-out", str(crt), "-subj", f"/O=Test/CN={cn}", "-days", "2")
    pub = openssl("x509", "-in", str(crt), "-pubkey", "-noout")
    return crt.read_bytes(), sha(openssl("pkey", "-pubin", "-outform", "DER", data=pub)).hex()


def key_node(n, e, hint, required="conf", algo="sha256,rsa3072"):
    props = [("key-name-hint", s(hint)), ("algo", s(algo))]
    if required is not None:
        props.append(("required", s(required)))
    props += [("rsa,num-bits", u32(n.bit_length())),
              ("rsa,modulus", n.to_bytes((n.bit_length() + 7) // 8, "big")),
              ("rsa,exponent", struct.pack(">Q", e))]
    return (props, [])


def make_itb(keys, version=VER_A):
    ctl = fdt(([], [("signature", ([], keys))]))
    uboot = b"\x00junk\x00" + version + b"\x00more\x00"
    root = ([("description", s("u-boot"))], [
        ("images", ([], [("uboot", image(uboot)), ("fdt-1", image(ctl))])),
        ("configurations", ([("default", s("config-1"))], [
            ("config-1", ([("firmware", s("uboot")), ("fdt", s("fdt-1"))], []))])),
    ])
    return fdt(root)


def make_fit(hint="test", signed=True, kernel=b"KERNEL" * 100):
    sig = [("signature-1", ([("algo", s("sha256,rsa3072")), ("key-name-hint", s(hint))], []))]
    root = ([], [
        ("images", ([], [
            ("kernel-1", image(kernel, extra=[("load", u32(0x2000000))])),
            ("fdt-1", image(b"DTB" * 50)),
        ])),
        ("configurations", ([("default", s("conf-1"))], [
            ("conf-1", ([("kernel", s("kernel-1")), ("fdt", s("fdt-1"))],
                        sig if signed else []))])),
    ])
    return fdt(root)


def pcr_ref(fit_name, fit, itb_name, itb):
    vals = {str(i): hashlib.sha256(f"pcr{i}".encode()).hexdigest().upper() for i in range(10)}
    vals["1"] = {"A": "AA" * 32, "B": "bb" * 32}
    return {
        "format": "tactiq-pcr-reference/1",
        "bank": "sha256",
        "inputs": {fit_name: sha(fit).hex(), itb_name: sha(itb).hex(),
                   "extlinux-rock5a.conf": "00" * 32, "tactiq-boot-rock5a.env": "11" * 32},
        "pcr": vals,
        "components": {"cmdline": {"A": "console=ttyS2 root=/dev/mmcblk0p2 rauc.slot=A",
                                   "B": "console=ttyS2 root=/dev/mmcblk0p3 rauc.slot=B"}},
        "assumptions": ["SPL is unmeasured", "no initrd is loaded"],
    }


IDENTITY = (b'TACTIQ_OS_VERSION="2.1.0"\nTACTIQ_OS_CODENAME="hardened-edge"\n'
            b'TACTIQ_BUILD_MACHINE="tactiq-rock5a"\nTACTIQ_META_TACTIQ_GIT="v2.1.0-rc12"\n'
            b'TACTIQ_IMAGE_NAME="tactiq-image"\nTACTIQ_RELEASE_DATE="2026-09-23"\n')


class Case:
    """One set of input files in a temporary directory."""

    def __init__(self, d, keyring):
        self.d = d
        self.files = {}
        self.keyring = keyring

    def put(self, name, data):
        (self.d / name).write_bytes(data if isinstance(data, bytes) else data.encode())
        self.files[name] = self.d / name
        return self.d / name

    def run(self, *extra, out="rim.json"):
        args = [sys.executable, str(GEN),
                "--identity", str(self.files["tactiq-release-rock5a"]),
                "--pcr-reference", str(self.files["pcr-reference-rock5a.json"]),
                "--fit", str(self.files["fitImage-rock5a"]),
                "--uboot", str(self.files["u-boot-rock5a.itb"]),
                "--rauc-keyring", str(self.keyring),
                "--idbloader", str(self.files["idbloader-rock5a.img"]),
                "--witness", "build_label=20260923000000",
                "-o", str(self.d / out), *extra]
        r = subprocess.run(args, capture_output=True, text=True)
        return r, (self.d / out)


def build(root, keys, itb_keys=None, fit=None, idb_version=VER_A, ref_edit=None,
          keyring=None, identity=IDENTITY):
    d = Path(tempfile.mkdtemp(dir=root))
    c = Case(d, keyring)
    itb = make_itb(itb_keys if itb_keys is not None else keys)
    fitb = fit if fit is not None else make_fit()
    c.put("u-boot-rock5a.itb", itb)
    c.put("fitImage-rock5a", fitb)
    c.put("idbloader-rock5a.img", b"SPL\x00" + idb_version + b"\x00")
    c.put("tactiq-release-rock5a", identity)
    ref = pcr_ref("fitImage-rock5a", fitb, "u-boot-rock5a.itb", itb)
    if ref_edit:
        ref_edit(ref)
    c.put("pcr-reference-rock5a.json", json.dumps(ref, indent=2))
    return c


def expect_fail(name, case, needle, *extra):
    r, out = case.run(*extra)
    check(f"{name}: exits non-zero", r.returncode != 0, f"rc={r.returncode}")
    check(f"{name}: says why", needle in r.stderr, f"stderr={r.stderr.strip()!r}")
    check(f"{name}: writes nothing", not out.exists())


def main():
    try:
        import jsonschema
    except ImportError:
        raise SystemExit("jsonschema is required: pip install jsonschema")
    schema = json.loads(SCHEMA.read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    validator = jsonschema.Draft202012Validator(schema)

    pycache = REPO / "scripts" / "__pycache__"
    pycache_before = pycache.exists()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        n, e, fit_spki = rsa_key(root, "fit")
        ca1, ca1_spki = cert(root, "ca1", "Test RAUC CA one")
        ca2, ca2_spki = cert(root, "ca2", "Test RAUC CA two")
        (root / "keyring1.pem").write_bytes(ca1)
        (root / "keyring2.pem").write_bytes(ca1 + ca2)
        (root / "keyring0.pem").write_bytes(b"not a certificate\n")
        good_keys = [("key-test", key_node(n, e, "test"))]
        rel_root, rel_root_spki = cert(root, "relroot", "Test release root")
        (root / "relroot-only.pem").write_bytes(rel_root)
        (root / "two-roots.pem").write_bytes(rel_root + ca1)
        ima_pem, ima_spki = cert(root, "ima", "Test IMA signer")
        (root / "x509_ima.der").write_bytes(openssl("x509", "-outform", "DER", data=ima_pem))
        (root / "disclosures.txt").write_bytes(b"# platform facts\n\nOTP fuses of the reference platform: test line\n")
        (root / "disclosures-empty.txt").write_bytes(b"# nothing\n\n")
        full = ("--release-root", str(root / "relroot-only.pem"),
                "--ima-cert", str(root / "x509_ima.der"),
                "--disclosures", str(root / "disclosures.txt"))

        # --- the good path --------------------------------------------------
        c = build(root, good_keys, keyring=root / "keyring1.pem")
        r, out = c.run(*full)
        check("good: exits 0", r.returncode == 0, r.stderr.strip())
        if r.returncode == 0:
            raw = out.read_bytes()
            rim = json.loads(raw)
            errs = [e.message for e in validator.iter_errors(rim)]
            check("good: validates against rim-v1.json", not errs, "; ".join(errs))
            fk = rim["keys"]["fit"]["keys"]
            check("good: one FIT key", len(fk) == 1, str(fk))
            check("good: FIT SPKI matches openssl", fk and fk[0]["spki_sha256"] == fit_spki,
                  f"{fk[0]['spki_sha256'] if fk else None} != {fit_spki}")
            check("good: FIT key bits", fk and fk[0]["bits"] == 3072)
            check("good: FIT signed_with", rim["keys"]["fit"]["signed_with"] == ["test"])
            rc = rim["keys"]["rauc_keyring"]["certificates"]
            check("good: RAUC SPKI matches openssl",
                  [x["spki_sha256"] for x in rc] == [ca1_spki], str(rc))
            check("good: RAUC subject", rc and "Test RAUC CA one" in rc[0]["subject"], str(rc))
            ref = json.loads(c.files["pcr-reference-rock5a.json"].read_text())
            want = {k: ([v.lower()] if isinstance(v, str) else {s_: x.lower() for s_, x in v.items()})
                    for k, v in ref["pcr"].items()}
            check("good: PCR values copied as sets, lower-cased", rim["pcr"]["values"] == want)
            check("good: canonical serialization (5.5)",
                  raw == json.dumps(rim, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False).encode("utf-8"))
            check("good: kernel command line per slot in clear",
                  rim["pcr"].get("cmdline") == ref["components"]["cmdline"])
            check("good: disclosures = reference assumptions, then file lines",
                  rim.get("disclosures") == ref["assumptions"] + ["OTP fuses of the reference platform: test line"],
                  str(rim.get("disclosures")))
            check("good: release root SPKI matches openssl",
                  rim["keys"].get("release_root", {}).get("spki_sha256") == rel_root_spki)
            ima = rim["keys"].get("ima", {})
            check("good: IMA certificate (DER) SPKI matches openssl",
                  [x["spki_sha256"] for x in ima.get("certificates", [])] == [ima_spki], str(ima))
            check("good: IMA path", ima.get("path") == "/etc/keys/x509_ima.der")
            check("good: selection 0-9", rim["pcr"]["selection"] == list(range(10)))
            check("good: reference digest",
                  rim["pcr"]["reference"]["sha256"] == sha(c.files["pcr-reference-rock5a.json"].read_bytes()).hex())
            check("good: identity fields unquoted",
                  rim["identity"]["fields"].get("TACTIQ_IMAGE_NAME") == "tactiq-image")
            check("good: chain_root is idbloader",
                  rim.get("chain_root", {}).get("sha256") == sha(c.files["idbloader-rock5a.img"].read_bytes()).hex())
            check("good: witness", rim["witness"] == {"build_label": "20260923000000"})
            check("good: no build-host path in output", str(root).encode() not in raw)
            r2, out2 = c.run(*full, out="rim2.json")
            check("good: byte-identical on a second run",
                  r2.returncode == 0 and out2.read_bytes() == raw)

        # --- the minimal run: no root, no IMA, no extra disclosures ----------
        r, out = c.run(out="rim-min.json")
        check("minimal: exits 0", r.returncode == 0, r.stderr.strip())
        if r.returncode == 0:
            m = json.loads(out.read_text())
            errs = [e.message for e in validator.iter_errors(m)]
            check("minimal: validates against rim-v1.json", not errs, "; ".join(errs))
            check("minimal: no ima, no release_root",
                  "ima" not in m["keys"] and "release_root" not in m["keys"])

        # --- selection narrower than the reference --------------------------
        r, out = c.run("--selection", "0-7,9", out="rim-sel.json")
        check("selection 0-7,9: exits 0", r.returncode == 0, r.stderr.strip())
        if r.returncode == 0:
            v = json.loads(out.read_text())["pcr"]
            check("selection 0-7,9: carries exactly those",
                  v["selection"] == [0, 1, 2, 3, 4, 5, 6, 7, 9] and sorted(v["values"], key=int) == [str(i) for i in v["selection"]])

        # --- keyring with two certificates ----------------------------------
        c2 = build(root, good_keys, keyring=root / "keyring2.pem")
        r, out = c2.run()
        check("two-cert keyring: exits 0", r.returncode == 0, r.stderr.strip())
        if r.returncode == 0:
            got = [x["spki_sha256"] for x in json.loads(out.read_text())["keys"]["rauc_keyring"]["certificates"]]
            check("two-cert keyring: both, in order", got == [ca1_spki, ca2_spki], str(got))

        # --- gates ----------------------------------------------------------
        kr = root / "keyring1.pem"
        fit_other = make_fit(kernel=b"OTHER" * 100)
        expect_fail("FIT not the one the reference was computed from",
                    build(root, good_keys, keyring=kr,
                          ref_edit=lambda ref: ref["inputs"].__setitem__("fitImage-rock5a", "00" * 32)),
                    "differs from the file")
        expect_fail("FIT not among reference inputs",
                    build(root, good_keys, keyring=kr,
                          ref_edit=lambda ref: ref["inputs"].pop("fitImage-rock5a")),
                    "is not among the inputs")
        expect_fail("u-boot.itb not the one the reference was computed from",
                    build(root, good_keys, keyring=kr,
                          ref_edit=lambda ref: ref["inputs"].__setitem__("u-boot-rock5a.itb", "00" * 32)),
                    "differs from the file")
        expect_fail("verification key not required",
                    build(root, good_keys, keyring=kr,
                          itb_keys=[("key-test", key_node(n, e, "test", required=None))]),
                    "not marked required")
        expect_fail("FIT signed with a key U-Boot does not carry",
                    build(root, good_keys, keyring=kr, fit=make_fit(hint="someone-else")),
                    "not in the control device tree")
        expect_fail("unsigned FIT",
                    build(root, good_keys, keyring=kr, fit=make_fit(signed=False)),
                    "carries no signature")
        expect_fail("non-RSA key node",
                    build(root, good_keys, keyring=kr,
                          itb_keys=[("key-test", ([("key-name-hint", s("test")),
                                                   ("algo", s("sha256,ecdsa256")),
                                                   ("required", s("conf"))], []))]),
                    "is not an RSA key")
        expect_fail("SPL from another U-Boot build",
                    build(root, good_keys, keyring=kr, idb_version=VER_B),
                    "SPL version differs")
        expect_fail("selection wider than the reference",
                    build(root, good_keys, keyring=kr), "has no value for PCR", "--selection", "0-10")
        expect_fail("PCR value that is not a digest",
                    build(root, good_keys, keyring=kr,
                          ref_edit=lambda ref: ref["pcr"].__setitem__("4", "zz" * 32)),
                    "is not 64 hex digits")
        expect_fail("PCR reference of another format",
                    build(root, good_keys, keyring=kr,
                          ref_edit=lambda ref: ref.__setitem__("format", "something-else/1")),
                    "unknown format")
        expect_fail("keyring without a certificate",
                    build(root, good_keys, keyring=root / "keyring0.pem"), "no PEM or DER certificate")
        expect_fail("identity line that is not KEY=VALUE",
                    build(root, good_keys, keyring=kr, identity=IDENTITY + b"garbage\n"),
                    "not KEY=VALUE")
        expect_fail("witness with an upper-case key",
                    build(root, good_keys, keyring=kr), "--witness", "--witness", "Tag=x")
        expect_fail("reference without command lines for the PCR 1 slots",
                    build(root, good_keys, keyring=kr,
                          ref_edit=lambda ref: ref.pop("components")),
                    "components.cmdline does not name the slots")
        expect_fail("reference whose command lines name other slots",
                    build(root, good_keys, keyring=kr,
                          ref_edit=lambda ref: ref["components"]["cmdline"].pop("B")),
                    "components.cmdline does not name the slots")
        expect_fail("reference without assumptions",
                    build(root, good_keys, keyring=kr,
                          ref_edit=lambda ref: ref.pop("assumptions")),
                    "no assumptions stated")
        expect_fail("release root file with two certificates",
                    build(root, good_keys, keyring=kr), "expected one certificate",
                    "--release-root", str(root / "two-roots.pem"))
        expect_fail("disclosures file with no lines",
                    build(root, good_keys, keyring=kr), "no disclosure lines",
                    "--disclosures", str(root / "disclosures-empty.txt"))
        del fit_other

    check("no __pycache__ left in scripts/",
          pycache_before or not pycache.exists(),
          "mk-rim.py wrote bytecode into the repo tree")

    print(f"{checks} checks, {len(failures)} failed")
    for f in failures:
        print(f"FAIL {f}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
