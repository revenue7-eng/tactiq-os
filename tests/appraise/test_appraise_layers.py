#!/usr/bin/env python3
"""Tests for scripts/appraise-layers.py.

What this guards
----------------
appraise-layers.py turns one TPM quote, its logs and a signed RIM into the
per-layer outcomes of trace-spec section 3.1.5, and records which route
established each layer: the layer's event log, the RIM, or both. Its failure
modes are quiet: a layer reported established on a route that did not hold, a
separator-only layer reported as measured, a RIM accepted from the wrong signer,
a log that does not replay hidden behind a matching reference.

Evidence: the committed quote in measurements/tpm-quotes-dev-20261015 (rc14
development image, PCR 0 to 12, TCG2 boot log and IMA log). RIMs are built here
from that quote's own PCR values and signed with the development hierarchy in
pki/dev, so each case knows exactly which layers a reference should match.

Needs: python3, openssl, tpm2_checkquote (tpm2-tools).
Run: python3 tests/appraise/test_appraise_layers.py
"""

import importlib.util
import json
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True

REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "scripts" / "appraise-layers.py"
EV = REPO / "measurements" / "tpm-quotes-dev-20261015"
PKI = REPO / "pki" / "dev"
NONCE = "8d61166e0b06211c22559c62d3bcb9d7c5d88b126818cc063ced5babc90288d4"

spec = importlib.util.spec_from_file_location("appraise_layers", TOOL)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

fails = 0


def check(name, cond, detail=""):
    global fails
    print(f"{'ok  ' if cond else 'FAIL'} {name}{'' if cond else ': ' + detail}")
    fails += not cond


def quote_values():
    att = tool.parse_attest((EV / "quote.msg").read_bytes())
    return tool.pcr_file((EV / "quote.pcr").read_bytes(), att["sel"])


def make_rim(d, name, values, signer="rim-signer", alter=None, sel=range(10)):
    vals = {str(i): [values[i].hex()] for i in sel}
    for i, v in (alter or {}).items():
        vals[str(i)] = [v]
    rim = d / f"{name}.json"
    rim.write_text(json.dumps({"pcr": {"selection": list(sel), "values": vals}}))
    subprocess.run(
        ["openssl", "cms", "-sign", "-binary", "-noattr", "-md", "sha256",
         "-in", str(rim), "-signer", str(PKI / f"{signer}.pem"),
         "-inkey", str(PKI / f"{signer}.key.pem"), "-certfile", str(PKI / "signing-ca.pem"),
         "-outform", "DER", "-out", str(rim) + ".p7s"], check=True, capture_output=True)
    return rim


def run(d, *extra, pcr=True, logs=True, rim=None, root=None, attest=None, sig=None):
    out = d / "out.json"
    cmd = [sys.executable, "-I", str(TOOL), "--ak", str(EV / "ak.pub"),
           "--attest", str(attest or EV / "quote.msg"), "--sig", str(sig or EV / "quote.sig"),
           "--json", str(out)]
    if pcr:
        cmd += ["--pcr", str(EV / "quote.pcr")]
    if logs:
        cmd += ["--bios-log", str(logs if isinstance(logs, Path) else EV / "quote.bios.log"),
                "--ima-log", str(EV / "quote.ima.log")]
    if rim:
        cmd += ["--rim", str(rim), "--rim-p7s", str(rim) + ".p7s",
                "--root", str(root or PKI / "root-ca.pem")]
    r = subprocess.run(cmd + list(extra), capture_output=True, text=True)
    res = json.loads(out.read_text()) if out.exists() and r.returncode != 1 else None
    if out.exists():
        out.unlink()
    return r.returncode, r.stdout, res


def layer(res, n):
    return ((res or {}).get("platform_measurement") or {}).get("layers", {}).get(f"pcr:{n}")


def main():
    for t in ("openssl", "tpm2_checkquote"):
        if not shutil.which(t):
            print(f"NOT ESTABLISHED: {t} is missing")
            return 2
    values = quote_values()
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        rim_all = make_rim(d, "all", values)
        rim_8 = make_rim(d, "pcr8", values, alter={8: "11" * 32})
        # Release RIMs select PCR 0 to 9, as the agent's quotes do. This quote selects
        # PCR 0 to 12, so the composite path needs a RIM over the same selection.
        rim_13 = make_rim(d, "all13", values, sel=range(13))
        rim_13_8 = make_rim(d, "pcr8-13", values, alter={8: "11" * 32}, sel=range(13))

        rc, out, res = run(d, "--qualifying-hex", NONCE,
                           "--require", "pcr:0,pcr:8,pcr:10,pcr:12")
        check("log route alone establishes the measured layers", rc == 0, out)
        check("separator-only PCR 2, 3, 5, 7 are layer-not-measured",
              all(layer(res, n) == {"outcome": "not-established", "reason": "layer-not-measured"}
                  for n in (2, 3, 5, 7)), json.dumps(res))
        check("reset-value PCR 11 is layer-not-measured",
              layer(res, 11) == {"outcome": "not-established", "reason": "layer-not-measured"})
        check("routes without a RIM are log only", res and res["routes"]["pcr:0"] == ["log"])

        rc, out, res = run(d, "--require", "pcr:0=both,pcr:8=both", rim=rim_all)
        check("matching RIM plus log gives both routes", rc == 0 and
              res["routes"]["pcr:0"] == ["log", "reference"], out)
        block = res["platform_measurement"]
        check("the 3.1.5 block carries outcome and reason only",
              all(set(v) <= {"outcome", "reason"} for v in block["layers"].values()))
        exp = "sha256:" + tool.hashlib.sha256(
            b"".join(values[i] for i in sorted(values))).hexdigest()
        check("the 3.1.5 measurement is the composite of the quoted values",
              block["measurement"] == exp)

        rc, out, res = run(d, "--require", "pcr:8=both", rim=rim_8)
        check("a layer the RIM does not match keeps the log route only",
              rc == 2 and res["routes"]["pcr:8"] == ["log"], out)
        rc, out, res = run(d, "--require", "pcr:8", rim=rim_8)
        check("without a named route the log route is enough", rc == 0, out)

        rc, out, res = run(d, "--require", "pcr:0", pcr=False, logs=False, rim=rim_all)
        check("a RIM over another selection leaves the values unknown",
              rc == 2 and res["platform_measurement"] is None, out)
        rc, out, res = run(d, "--require", "pcr:0", pcr=False, logs=False, rim=rim_13)
        check("no logs, no .pcr: the composite matches the RIM and rats establishes by reference",
              rc == 0 and layer(res, 0) == {"outcome": "established"}
              and res["routes"]["pcr:0"] == ["reference"], out)
        rc, out, res = run(d, "--require", "pcr:0", "--definition", "trace-text",
                           pcr=False, logs=False, rim=rim_13)
        check("trace-text does not count the reference route", rc == 2 and layer(res, 0) is None,
              out)
        rc, out, res = run(d, "--require", "pcr:0", pcr=False, logs=False, rim=rim_13_8)
        check("no logs, composite matches no RIM composite: nothing is established",
              rc == 2 and res["platform_measurement"] is None, out)

        bad_log = d / "bios.log"
        b = bytearray((EV / "quote.bios.log").read_bytes())
        o = 8 + 20
        o += 4 + struct.unpack("<I", b[o:o + 4])[0]
        o += 12 + 2 + 20 + 2          # first event: header, SHA-1 digest, SHA-256 alg id
        b[o] ^= 1
        bad_log.write_bytes(b)
        rc, out, res = run(d, "--require", "pcr:0", logs=bad_log, rim=rim_all)
        check("a log that does not replay is evidence-spans-multiple-boots even if the RIM matches",
              rc == 2 and layer(res, 0) == {"outcome": "not-established",
                                            "reason": "evidence-spans-multiple-boots"}, out)

        rc, out, res = run(d, "--require", "pcr:0", "--policy", "appraised", rim=rim_all)
        check("policy appraised reports measured-not-appraised",
              rc == 2 and layer(res, 0) == {"outcome": "not-established",
                                            "reason": "measured-not-appraised"}, out)

        rc, out, _ = run(d, "--qualifying-hex", "00" * 32)
        check("wrong qualifying data fails", rc == 1, out)
        bad_sig = d / "quote.sig"
        s = bytearray((EV / "quote.sig").read_bytes())
        s[20] ^= 1
        bad_sig.write_bytes(s)
        rc, out, _ = run(d, sig=bad_sig)
        check("a tampered signature fails", rc == 1, out)
        tampered = d / "tampered.json"
        tampered.write_text(rim_all.read_text().replace(values[0].hex(), "22" * 32))
        shutil.copy(str(rim_all) + ".p7s", str(tampered) + ".p7s")
        rc, out, _ = run(d, rim=tampered)
        check("a RIM changed after signing fails", rc == 1, out)
        rim_ima = make_rim(d, "ima", values, signer="ima-signer")
        rc, out, _ = run(d, rim=rim_ima)
        check("a RIM signed by a leaf without the RIM Signer EKU fails", rc == 1, out)
        rc, out, _ = run(d, rim=rim_all, root=PKI / "signing-ca.pem")
        check("a RIM checked against another root fails", rc == 1, out)
        rc, out, _ = run(d, "--require", "pcr:0=maybe")
        check("an unknown route in --require fails", rc == 1, out)

    print(f"FAILED: {fails}" if fails else "ALL CHECKS PASSED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
