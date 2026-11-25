#!/usr/bin/env python3
"""Offline check of the TPM-bound key evidence of this directory.

Run from this directory:
    python3 check.py
Needs Python 3 and `cryptography`. No TPM and no network.

Checks, in order:
  1. ak.pub is the registered AK: its name equals REGISTERED_AK_NAME and its
     attributes carry fixedTPM, fixedParent, restricted and sign.
  2. certify.att is a TPM-generated TPM2_Certify (TPM_GENERATED_VALUE,
     TPM_ST_ATTEST_CERTIFY) signed by that AK, over the verifier nonce n1.hex.
  3. The certified name equals the name computed from bind.pub, and bind.pub
     carries fixedTPM, fixedParent, sensitiveDataOrigin and sign, is not
     restricted, and is an ECDSA P-256 / SHA-256 (ES256) key.
  4. pop.jwt is a DPoP proof (typ dpop+jwt, alg ES256) whose signature
     verifies under the JWK in its header, whose JWK is the key of bind.pub,
     whose nonce is n2.hex, and whose RFC 7638 thumbprint is printed as the
     cnf.jkt a grant would carry. pop.sig is the TPMT_SIGNATURE the TPM
     returned for the SHA-256 of pop.signing_input (pop.digest).
  5. Control and negatives built from the same files, each expected to be
     refused with one named reason:
       - exp.*: a key created without fixedTPM and fixedParent, certified by
         the same AK over n3.hex: refused as key_exportable although the AK
         signature verifies;
       - certify.att presented against the nonce of another challenge (n3):
         nonce_mismatch;
       - certify.att with one byte of the certified name changed:
         certify_signature_invalid;
       - pop.jwt with one character of the payload changed: pop_signature_invalid;
       - pop.jwt checked against a different expected nonce: pop_nonce_mismatch.

Exit status 0 when every check gives the expected result, 1 otherwise.
"""
import base64
import hashlib
import json
import struct
import sys

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

REGISTERED_AK_NAME = bytes.fromhex("000b35c0941662473b6dc78ce636d83dfcaf1bbdfa68bb69121dd9b3c0b414df0a0a")
TPM_GENERATED = 0xFF544347
TPM_ST_ATTEST_CERTIFY = 0x8017
FIXED_TPM, FIXED_PARENT, SENS_ORIGIN, RESTRICTED, SIGN = 1 << 1, 1 << 4, 1 << 5, 1 << 16, 1 << 18


def rd(name):
    with open(name, "rb") as fh:
        return fh.read()


def nonce(name):
    return bytes.fromhex(rd(name).decode().strip())


def b64u(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def ub64u(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def tpm2b(buf, off):
    (n,) = struct.unpack_from(">H", buf, off)
    return buf[off + 2: off + 2 + n], off + 2 + n


def parse_public(pub2b):
    area, _ = tpm2b(pub2b, 0)
    typ, _, attrs = struct.unpack_from(">HHI", area, 0)
    _, off = tpm2b(area, 8)
    _, scheme, scheme_hash, curve, _ = struct.unpack_from(">HHHHH", area, off)
    off += 10
    x, off = tpm2b(area, off)
    y, off = tpm2b(area, off)
    if typ != 0x0023 or off != len(area):
        raise ValueError("not a plain ECC public area")
    return dict(area=area, attrs=attrs, curve=curve, scheme=scheme, scheme_hash=scheme_hash, x=x, y=y)


def name_of(area):
    return b"\x00\x0b" + hashlib.sha256(area).digest()


def ecc_key(x, y):
    nums = ec.EllipticCurvePublicNumbers(int.from_bytes(x, "big"), int.from_bytes(y, "big"), ec.SECP256R1())
    return nums.public_key()


def tpm_sig_to_der(sig):
    alg, halg = struct.unpack_from(">HH", sig, 0)
    r, off = tpm2b(sig, 4)
    s, off = tpm2b(sig, off)
    if alg != 0x0018 or halg != 0x000B or off != len(sig):
        raise ValueError("not an ECDSA-SHA256 TPMT_SIGNATURE")
    return encode_dss_signature(int.from_bytes(r, "big"), int.from_bytes(s, "big"))


def parse_certify(att):
    magic, typ = struct.unpack_from(">IH", att, 0)
    _, off = tpm2b(att, 6)
    extra, off = tpm2b(att, off)
    clock, reset, restart, safe = struct.unpack_from(">QIIB", att, off)
    off += 17
    (fw,) = struct.unpack_from(">Q", att, off)
    off += 8
    name, off = tpm2b(att, off)
    _, off = tpm2b(att, off)
    if off != len(att):
        raise ValueError("trailing bytes in TPMS_ATTEST")
    return dict(magic=magic, type=typ, extra=extra, clock=clock, reset=reset, restart=restart, firmware=fw, name=name)


def check_certify(ak_pub, key_pub, att, sig, expected_nonce):
    """Reasons for refusing the bound key, in check order; empty means accepted."""
    fails = []
    ak = parse_public(ak_pub)
    if name_of(ak["area"]) != REGISTERED_AK_NAME:
        fails.append("ak_not_registered")
    need = FIXED_TPM | FIXED_PARENT | RESTRICTED | SIGN
    if ak["attrs"] & need != need:
        fails.append("ak_attributes")
    try:
        ecc_key(ak["x"], ak["y"]).verify(tpm_sig_to_der(sig), att, ec.ECDSA(hashes.SHA256()))
    except InvalidSignature:
        fails.append("certify_signature_invalid")
    a = parse_certify(att)
    if a["magic"] != TPM_GENERATED or a["type"] != TPM_ST_ATTEST_CERTIFY:
        fails.append("not_tpm_certify")
    if a["extra"] != expected_nonce:
        fails.append("nonce_mismatch")
    key = parse_public(key_pub)
    if name_of(key["area"]) != a["name"]:
        fails.append("key_not_certified")
    need = FIXED_TPM | FIXED_PARENT | SENS_ORIGIN | SIGN
    if key["attrs"] & need != need:
        fails.append("key_exportable")
    if key["attrs"] & RESTRICTED:
        fails.append("key_restricted")
    if (key["curve"], key["scheme"], key["scheme_hash"]) != (0x0003, 0x0018, 0x000B):
        fails.append("key_not_es256")
    return fails, a


def thumbprint(jwk):
    canon = json.dumps({k: jwk[k] for k in ("crv", "kty", "x", "y")}, separators=(",", ":"), sort_keys=True)
    return b64u(hashlib.sha256(canon.encode()).digest())


def check_pop(jwt, key_pub, expected_nonce_hex):
    """Reasons for refusing the proof of possession; empty means accepted."""
    fails = []
    h, p, s = jwt.split(".")
    hdr, pl = json.loads(ub64u(h)), json.loads(ub64u(p))
    if hdr.get("typ") != "dpop+jwt" or hdr.get("alg") != "ES256":
        fails.append("pop_header")
    jwk = hdr["jwk"]
    raw = ub64u(s)
    der = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
    try:
        ecc_key(ub64u(jwk["x"]), ub64u(jwk["y"])).verify(der, f"{h}.{p}".encode(), ec.ECDSA(hashes.SHA256()))
    except InvalidSignature:
        fails.append("pop_signature_invalid")
    key = parse_public(key_pub)
    if (ub64u(jwk["x"]), ub64u(jwk["y"])) != (key["x"], key["y"]):
        fails.append("pop_key_not_bound_key")
    if pl.get("nonce") != expected_nonce_hex:
        fails.append("pop_nonce_mismatch")
    return fails, thumbprint(jwk)


def main():
    results = []

    def expect(label, fails, want):
        ok = fails == want
        results.append(ok)
        got = ", ".join(fails) if fails else "accept"
        print(f"{'ok  ' if ok else 'FAIL'} {label}: {got}" + ("" if ok else f" (expected {', '.join(want) or 'accept'})"))

    ak_pub, bind_pub = rd("ak.pub"), rd("bind.pub")
    att, sig = rd("certify.att"), rd("certify.sig")
    n1, n2, n3 = nonce("n1.hex"), rd("n2.hex").decode().strip(), nonce("n3.hex")

    fails, a = check_certify(ak_pub, bind_pub, att, sig, n1)
    expect("bound key certified by the registered AK over n1", fails, [])
    print(f"     certified name {a['name'].hex()}, firmware {a['firmware']:016x}, "
          f"resetCount {a['reset']}, restartCount {a['restart']}, clock {a['clock']} ms")

    jwt = rd("pop.jwt").decode().strip()
    fails, jkt = check_pop(jwt, bind_pub, n2)
    expect("DPoP proof signed in the TPM by the bound key over n2", fails, [])
    print(f"     cnf.jkt {jkt}")

    si = rd("pop.signing_input").decode()
    digest_ok = hashlib.sha256(si.encode()).digest() == rd("pop.digest")
    tpm_sig_ok = True
    try:
        k = parse_public(bind_pub)
        ecc_key(k["x"], k["y"]).verify(tpm_sig_to_der(rd("pop.sig")), si.encode(), ec.ECDSA(hashes.SHA256()))
    except InvalidSignature:
        tpm_sig_ok = False
    expect("pop.sig is the TPM signature over pop.digest", [] if (digest_ok and tpm_sig_ok) else ["pop_tpm_signature"], [])
    r, off = tpm2b(rd("pop.sig"), 4)
    s_, _ = tpm2b(rd("pop.sig"), off)
    jws_sig = b64u(r.rjust(32, b"\0") + s_.rjust(32, b"\0"))
    expect("pop.jwt signature is pop.sig", [] if jwt.split(".")[2] == jws_sig else ["pop_jwt_not_pop_sig"], [])

    fails, _ = check_certify(ak_pub, rd("exp.pub"), rd("exp.att"), rd("exp.sig"), n3)
    expect("control: exportable key certified by the same AK over n3", fails, ["key_exportable"])

    fails, _ = check_certify(ak_pub, bind_pub, att, sig, n3)
    expect("negative: certify.att against another challenge", fails, ["nonce_mismatch"])

    bad = bytearray(att)
    bad[-40] ^= 1
    fails, _ = check_certify(ak_pub, bind_pub, bytes(bad), sig, n1)
    expect("negative: certified name edited", fails, ["certify_signature_invalid", "key_not_certified"])

    h, p, s = jwt.split(".")
    pl = json.loads(ub64u(p))
    pl["htm"] = "GET"
    fails, _ = check_pop(".".join([h, b64u(json.dumps(pl, separators=(",", ":")).encode()), s]), bind_pub, n2)
    expect("negative: DPoP payload edited", fails, ["pop_signature_invalid"])

    fails, _ = check_pop(jwt, bind_pub, n3.hex())
    expect("negative: DPoP proof against another challenge", fails, ["pop_nonce_mismatch"])

    passed = sum(results)
    print(f"{'PASSED' if all(results) else 'FAILED'}: {passed} of {len(results)} checks gave the expected result")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
