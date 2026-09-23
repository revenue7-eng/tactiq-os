#!/usr/bin/env python3
"""
mk-rim.py: build the Reference Integrity Manifest (RIM) of one TactiQ OS
release for one board.

The RIM is the statement a verifier matches a device against:

  identity    fields of /etc/tactiq-release as shipped in the release set
              (tactiq-release-<board>); the selection key of the RIM
  witness     facts about the build that take no part in selection (full tag
              SHA, build label), given with --witness key=value
  pcr         for every selected PCR its set of expected sha256 values, copied
              from pcr-reference-<board>.json (PCR 1 keyed by slot), and the
              kernel command line of each slot in clear so PCR 1 can be
              recomputed rather than trusted (RELEASE_INTEGRITY.md 5.3, 5.4)
  keys        sha256 of the SubjectPublicKeyInfo of every FIT verification key
              in the control device tree inside u-boot.itb, of every
              certificate in the RAUC keyring and, where one is installed, the
              IMA keyring certificate, both taken from the rootfs, and of the
              release root certificate
  disclosures the assumptions under which the values hold: those stated in
              the PCR reference, then the lines of --disclosures
  chain_root  sha256 of idbloader.img. SPL is the unmeasured root of the
              measurement chain, so no PCR sees it; a verifier checks it
              against the boot medium instead (optional, --idbloader)

Consistency gates: the FIT image and u-boot.itb must be byte-identical to the
files the PCR reference was computed from; every key-name-hint that signs the
default FIT configuration must be present in the control device tree and
marked required; the SPL version string must match U-Boot; with --agent-unit,
the PCR set the attestation agent quotes (TACTIQ_PCR_SPEC in its systemd unit,
last assignment wins) must equal the selection in the same bank.

This script only writes JSON. Signing (CMS, detached, DER, -noattr, sha256)
is done by mk-release.sh. Output is canonical (RELEASE_INTEGRITY.md 5.5):
UTF-8, sorted keys, no insignificant whitespace, no trailing newline;
lower-case hex, basenames only, no build-host paths.

FDT parsing is shared with mk-pcr-reference.py, loaded from this directory.
"""
import argparse
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys

sys.dont_write_bytecode = True  # mk-rim.py runs from the repo tree; leave no __pycache__ there
HERE = os.path.dirname(os.path.abspath(__file__))
FORMAT = "tactiq-rim/1"
base = os.path.basename


def load_pcrref():
    path = os.path.join(HERE, "mk-pcr-reference.py")
    try:
        src = open(path, encoding="utf-8").read()
    except OSError as e:
        sys.exit(f"mk-rim: cannot read {path}: {e}")
    if not re.search(r"""if __name__ == ['"]__main__['"]""", src):
        sys.exit(f"mk-rim: {path} has no __main__ guard; importing it would run it")
    spec = importlib.util.spec_from_file_location("mk_pcr_reference", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


P = load_pcrref()
sha, read, pstr, pu32 = P.sha, P.read, P.pstr, P.pu32
HEX64 = re.compile(r"[0-9a-fA-F]{64}")


def die(msg):
    sys.exit(f"mk-rim: error: {msg}")


# --- DER, just enough for an RSA SubjectPublicKeyInfo ----------------------
def der(tag, body):
    n = len(body)
    if n < 0x80:
        ln = bytes([n])
    else:
        b = n.to_bytes((n.bit_length() + 7) // 8, "big")
        ln = bytes([0x80 | len(b)]) + b
    return bytes([tag]) + ln + body


def der_uint(v):
    # bit_length // 8 + 1 bytes: minimal, with a leading 0x00 when the top bit is set
    return der(0x02, v.to_bytes(v.bit_length() // 8 + 1, "big"))


RSA_ALGID = der(0x30, bytes.fromhex("06092a864886f70d010101") + b"\x05\x00")


def rsa_spki(n, e):
    rsapub = der(0x30, der_uint(n) + der_uint(e))
    return der(0x30, RSA_ALGID + der(0x03, b"\x00" + rsapub))


# --- FIT verification keys from the control device tree --------------------
def image_data(buf, totalsize, img, label):
    hashed = any(pstr(n, "algo") == "sha256"
                 for k, n in img["nodes"].items() if k.startswith("hash"))
    if hashed:
        return P.fit_payload(buf, totalsize, img, label)[0]
    pr = img["props"]
    if "data" in pr:
        return pr["data"]
    if "data-size" not in pr:
        die(f"{label}: image node has no data")
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
    return data


def fit_keys(path):
    buf = read(path)
    root, totalsize = P.parse_fdt(buf)
    images = root["nodes"].get("images")
    confs = root["nodes"].get("configurations")
    if images is None or confs is None:
        die(f"{base(path)}: no /images or /configurations")
    default = pstr(confs, "default")
    if default is None or default not in confs["nodes"]:
        die(f"{base(path)}: no usable default configuration")
    fname = pstr(confs["nodes"][default], "fdt")
    if fname is None or fname not in images["nodes"]:
        die(f"{base(path)}: configuration {default} names no fdt image")
    ctl, _ = P.parse_fdt(image_data(buf, totalsize, images["nodes"][fname], fname))
    sig = ctl["nodes"].get("signature")
    if sig is None:
        die(f"{base(path)}: control device tree {fname} has no /signature node")
    keys = []
    for name, node in sorted(sig["nodes"].items()):
        pr = node["props"]
        if "rsa,modulus" not in pr or "rsa,exponent" not in pr:
            die(f"{base(path)}: /signature/{name} is not an RSA key "
                f"(algo {pstr(node, 'algo')!r})")
        n = int.from_bytes(pr["rsa,modulus"], "big")
        e = int.from_bytes(pr["rsa,exponent"], "big")
        keys.append({
            "node": name,
            "key_name_hint": pstr(node, "key-name-hint"),
            "algo": pstr(node, "algo"),
            "required": pstr(node, "required"),
            "bits": n.bit_length(),
            "spki_sha256": sha(rsa_spki(n, e)).hex(),
        })
    if not keys:
        die(f"{base(path)}: /signature has no key nodes")
    return keys


# --- RAUC keyring ----------------------------------------------------------
PEM_CERT = re.compile(rb"-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----", re.S)


def openssl(args, data):
    r = subprocess.run(["openssl", *args], input=data, capture_output=True)
    if r.returncode:
        die(f"openssl {' '.join(args)}: {r.stderr.decode(errors='replace').strip()}")
    return r.stdout


def certs(path):
    raw = read(path)
    blocks = PEM_CERT.findall(raw)
    if not blocks and raw[:1] == b"\x30":
        blocks = [openssl(["x509", "-inform", "DER", "-outform", "PEM"], raw)]
    if not blocks:
        die(f"{base(path)}: no PEM or DER certificate")
    out = []
    for b in blocks:
        pub = openssl(["x509", "-pubkey", "-noout"], b)
        spki = openssl(["pkey", "-pubin", "-outform", "DER"], pub)
        subj = openssl(["x509", "-noout", "-subject", "-nameopt", "RFC2253"], b)
        out.append({
            "subject": subj.decode().strip().removeprefix("subject="),
            "spki_sha256": sha(spki).hex(),
        })
    return out


# --- identity, witness, selection -------------------------------------------
def read_identity(path):
    fields = {}
    for ln in read(path).decode().splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        k, sep, v = ln.partition("=")
        if not sep or not re.fullmatch(r"[A-Z][A-Z0-9_]*", k):
            die(f"{base(path)}: not KEY=VALUE: {ln!r}")
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        if k in fields:
            die(f"{base(path)}: {k} given twice")
        fields[k] = v
    if not fields:
        die(f"{base(path)}: empty")
    return fields


def parse_witness(items):
    w = {}
    for it in items:
        k, sep, v = it.partition("=")
        if not sep or not re.fullmatch(r"[a-z][a-z0-9_]*", k) or not v:
            die(f"--witness wants key=value with a lower-case key, got {it!r}")
        if k in w:
            die(f"--witness {k} given twice")
        w[k] = v
    return w


def parse_selection(s):
    sel = set()
    for part in s.split(","):
        a, _, b = part.strip().partition("-")
        try:
            lo = int(a)
            hi = int(b) if b else lo
        except ValueError:
            die(f"--selection: bad range {part!r}")
        if not 0 <= lo <= hi <= 23:
            die(f"--selection: range {part!r} outside 0-23")
        sel.update(range(lo, hi + 1))
    return sorted(sel)


def norm_hex(v, what):
    # the PCR reference prints digests upper-case (tpm2_pcrread style); the RIM
    # carries them lower-case, compared as bytes
    if isinstance(v, dict):
        return {k: norm_hex(x, f"{what} {k}") for k, x in v.items()}
    if not isinstance(v, str) or not HEX64.fullmatch(v):
        die(f"{what}: {v!r} is not 64 hex digits")
    return v.lower()


def read_disclosures(path):
    out = []
    for ln in read(path).decode().splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#"):
            out.append(ln)
    if not out:
        die(f"{base(path)}: no disclosure lines")
    return out


def agent_pcr_spec(path):
    # systemd semantics: Environment= lines accumulate, a later assignment of
    # the same variable wins; values may be quoted
    spec = None
    for ln in read(path).decode().splitlines():
        ln = ln.strip()
        if not ln.startswith("Environment="):
            continue
        try:
            toks = shlex.split(ln[len("Environment="):])
        except ValueError as e:
            die(f"{base(path)}: unparseable Environment= line: {e}")
        for t in toks:
            k, sep, v = t.partition("=")
            if sep and k == "TACTIQ_PCR_SPEC":
                spec = v
    return spec


def parse_agent_spec(spec, where):
    # the agent's own grammar (tactiq-attest prover, tpm::parse_pcr_spec):
    # "<alg>:<i>,<j>,..." with strictly increasing indices, no ranges, one bank
    alg, sep, lst = spec.partition(":")
    if not sep or "+" in spec:
        die(f"{where}: TACTIQ_PCR_SPEC {spec!r} is not <alg>:<pcr,...> over one bank")
    idx = []
    for tok in lst.split(","):
        tok = tok.strip()
        if not tok.isdigit() or int(tok) > 23:
            die(f"{where}: TACTIQ_PCR_SPEC {spec!r}: bad PCR index {tok!r}")
        if idx and int(tok) <= idx[-1]:
            die(f"{where}: TACTIQ_PCR_SPEC {spec!r}: indices must increase")
        idx.append(int(tok))
    return alg.strip(), idx


def check_input(ref, ref_path, path):
    want = ref.get("inputs", {}).get(base(path))
    if want is None:
        die(f"{base(path)} is not among the inputs of {base(ref_path)}")
    if want != sha(read(path)).hex():
        die(f"{base(path)} differs from the file {base(ref_path)} was computed from")


def main():
    ap = argparse.ArgumentParser(description="Build the TactiQ OS RIM (JSON, unsigned).")
    ap.add_argument("--identity", required=True, help="tactiq-release-<board> from the release set")
    ap.add_argument("--pcr-reference", required=True, help="pcr-reference-<board>.json")
    ap.add_argument("--fit", required=True, help="fitImage-<board> the PCR reference was computed from")
    ap.add_argument("--uboot", required=True, help="u-boot-<board>.itb")
    ap.add_argument("--rauc-keyring", required=True,
                    help="the RAUC keyring file extracted from the rootfs")
    ap.add_argument("--rauc-keyring-path", default="/etc/rauc/root-ca.pem",
                    help="where the keyring lives in the rootfs (system.conf [keyring] path)")
    ap.add_argument("--ima-cert", help="the IMA keyring certificate extracted from the rootfs, if installed")
    ap.add_argument("--ima-cert-path", default="/etc/keys/x509_ima.der",
                    help="where the IMA certificate lives in the rootfs (CONFIG_IMA_X509_PATH)")
    ap.add_argument("--release-root", help="the release root certificate (PEM)")
    ap.add_argument("--disclosures", help="file of further disclosure lines (platform facts "
                    "the build cannot know, e.g. OTP state); # comments ignored")
    ap.add_argument("--idbloader", help="idbloader-<board>.img; recorded as chain_root")
    ap.add_argument("--selection", default="0-9", help="PCR indices, e.g. 0-9 or 0-7,9")
    ap.add_argument("--agent-unit", help="the attestation agent's systemd unit from the release "
                    "rootfs; its TACTIQ_PCR_SPEC must equal the selection")
    ap.add_argument("--witness", action="append", default=[], metavar="key=value")
    ap.add_argument("-o", "--output", required=True)
    a = ap.parse_args()

    ref = json.loads(read(a.pcr_reference))
    if ref.get("format") != "tactiq-pcr-reference/1":
        die(f"{base(a.pcr_reference)}: unknown format {ref.get('format')!r}")
    if ref.get("bank") != "sha256":
        die(f"{base(a.pcr_reference)}: bank {ref.get('bank')!r}, expected sha256")
    check_input(ref, a.pcr_reference, a.fit)
    check_input(ref, a.pcr_reference, a.uboot)

    selection = parse_selection(a.selection)
    missing = [i for i in selection if str(i) not in ref["pcr"]]
    if missing:
        die(f"selection {selection}: {base(a.pcr_reference)} has no value for PCR {missing}")
    if a.agent_unit:
        spec = agent_pcr_spec(a.agent_unit)
        if spec is None:
            die(f"{base(a.agent_unit)}: no TACTIQ_PCR_SPEC; the agent would quote its built-in "
                f"default, which this RIM cannot see")
        alg, idx = parse_agent_spec(spec, base(a.agent_unit))
        if alg != ref["bank"] or idx != selection:
            die(f"{base(a.agent_unit)}: the agent quotes {spec}, the RIM selects "
                f"{ref['bank']}:{','.join(map(str, selection))}; no envelope from the device "
                f"could match these values")
    values = {}
    for i in selection:
        v = norm_hex(ref["pcr"][str(i)], f"PCR {i}")
        values[str(i)] = v if isinstance(v, dict) else [v]
    cmdline = ref.get("components", {}).get("cmdline")
    slots = values.get("1")
    if slots is not None:
        if not isinstance(slots, dict):
            die(f"{base(a.pcr_reference)}: PCR 1 is not keyed by slot")
        if not isinstance(cmdline, dict) or sorted(cmdline) != sorted(slots):
            die(f"{base(a.pcr_reference)}: components.cmdline does not name the slots of PCR 1 "
                f"({sorted(slots)})")
        for sl, c in cmdline.items():
            if not isinstance(c, str) or not c:
                die(f"{base(a.pcr_reference)}: empty command line for slot {sl}")
    assumptions = ref.get("assumptions")
    if not isinstance(assumptions, list) or not assumptions or \
            not all(isinstance(x, str) and x for x in assumptions):
        die(f"{base(a.pcr_reference)}: no assumptions stated")
    disclosures = list(assumptions)
    if a.disclosures:
        disclosures += read_disclosures(a.disclosures)

    keys = fit_keys(a.uboot)
    hints = [h for h in P.read_fit(a.fit)["key_name_hint"] if h]
    if not hints:
        die(f"{base(a.fit)}: default configuration carries no signature")
    for h in hints:
        match = [k for k in keys if k["key_name_hint"] == h]
        if not match:
            die(f"{base(a.fit)} is signed with {h!r}, which is not in the control "
                f"device tree of {base(a.uboot)}")
        if not any(k["required"] in ("conf", "image") for k in match):
            die(f"key {h!r} is in {base(a.uboot)} but not marked required: "
                f"U-Boot would boot an unsigned FIT")

    doc = {
        "format": FORMAT,
        "identity": {
            "file": base(a.identity),
            "sha256": sha(read(a.identity)).hex(),
            "fields": read_identity(a.identity),
        },
        "witness": parse_witness(a.witness),
        "pcr": {
            "bank": "sha256",
            "selection": selection,
            "values": values,
            "reference": {
                "file": base(a.pcr_reference),
                "sha256": sha(read(a.pcr_reference)).hex(),
            },
        },
        "disclosures": disclosures,
        "keys": {
            "fit": {
                "file": base(a.uboot),
                "signed_with": sorted(hints),
                "keys": keys,
            },
            "rauc_keyring": {
                "path": a.rauc_keyring_path,
                "certificates": certs(a.rauc_keyring),
            },
        },
    }
    if slots is not None:
        doc["pcr"]["cmdline"] = cmdline
    if a.ima_cert:
        doc["keys"]["ima"] = {"path": a.ima_cert_path, "certificates": certs(a.ima_cert)}
    if a.release_root:
        root = certs(a.release_root)
        if len(root) != 1:
            die(f"{base(a.release_root)}: expected one certificate, found {len(root)}")
        doc["keys"]["release_root"] = root[0]
    if a.idbloader:
        if P.uboot_version(a.idbloader) != P.uboot_version(a.uboot):
            die(f"{base(a.idbloader)}: SPL version differs from {base(a.uboot)}")
        doc["chain_root"] = {
            "file": base(a.idbloader),
            "sha256": sha(read(a.idbloader)).hex(),
        }

    out = json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    with open(a.output, "wb") as f:
        f.write(out.encode("utf-8"))


if __name__ == "__main__":
    main()
