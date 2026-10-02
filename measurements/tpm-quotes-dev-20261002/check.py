#!/usr/bin/env python3
"""Offline check of the 2026-10-02 development-loader quote pair.

Run from this directory with tpm2-tools on PATH:
    python3 check.py
It verifies both quotes under ak.pub with their qualifying data, reads
resetCount and the PCR selection from the signed TPMS_ATTEST, and replays
the IMA logs into PCR 10, 11 and 12. The logs were copied from
ascii_runtime_measurements, which carries SHA-1 template hashes; the
template data is rebuilt from the fields, checked against that SHA-1 for
every entry, and its SHA-256 is extended into the SHA-256 bank.
"""
import hashlib, struct, subprocess, sys

def tdata(f):
    alg, dig = f[3].split(':', 1)
    parts = (alg.encode() + b':\0' + bytes.fromhex(dig),
             f[4].encode() + b'\0',
             bytes.fromhex(f[5]) if len(f) > 5 else b'')
    return b''.join(struct.pack('<I', len(x)) + x for x in parts)

def attest(path):
    b = open(path, 'rb').read(); o = 6
    o += 2 + struct.unpack('>H', b[o:o + 2])[0]
    n = struct.unpack('>H', b[o:o + 2])[0]; extra = b[o + 2:o + 2 + n]; o += 2 + n
    clock, reset, restart, safe = struct.unpack('>QIIB', b[o:o + 17]); o += 17 + 8
    cnt = struct.unpack('>I', b[o:o + 4])[0]; o += 4; sel = []
    for _ in range(cnt):
        alg, sz = struct.unpack('>HB', b[o:o + 3]); o += 3
        bits = b[o:o + sz]; o += sz
        sel += [i * 8 + j for i in range(sz) for j in range(8) if bits[i] >> j & 1]
    return extra, reset, restart, sel

def pcr_values(path, sel):
    # tpm2_quote -o writes a TPML_PCR_SELECTION (132 bytes), a UINT32 count of
    # digest lists, then that many TPML_DIGEST structs (UINT32 count and eight
    # TPM2B_DIGEST slots of 2 + 64 bytes), little-endian. Values follow the
    # selection order.
    b = open(path, 'rb').read(); vals = []
    lists = struct.unpack('<I', b[132:136])[0]
    for i in range(lists):
        o = 136 + 532 * i
        cnt = struct.unpack('<I', b[o:o + 4])[0]
        for k in range(cnt):
            q = o + 4 + 66 * k
            size = struct.unpack('<H', b[q:q + 2])[0]
            vals.append(b[q + 2:q + 2 + size])
    return dict(zip(sel, vals))

fails = 0
for s in ('cold', 'warm'):
    extra, reset, restart, sel = attest(f'{s}.msg')
    r = subprocess.run(['tpm2_checkquote', '-u', 'ak.pub', '-m', f'{s}.msg',
                        '-s', f'{s}.sig', '-f', f'{s}.pcr', '-g', 'sha256',
                        '-q', extra.hex()], capture_output=True, text=True)
    ok = r.returncode == 0
    fails += not ok
    print(f'{s}: quote {"verifies" if ok else "FAILS"} under ak.pub, '
          f'qualifying data {extra.decode()!r}, resetCount {reset}, '
          f'restartCount {restart}, PCRs {sel[0]}-{sel[-1]}')
    pcr = pcr_values(f'{s}.pcr', sel)
    rep = {10: bytes(32), 11: bytes(32), 12: bytes(32)}; bad = 0; n = 0
    for line in open(f'{s}.ima.log'):
        f = line.split()
        if not f: continue
        n += 1
        try:
            td = tdata(f)
        except (ValueError, IndexError):
            bad += 1; continue
        if f[1] == '0' * 40:
            d = b'\xff' * 32
        else:
            bad += hashlib.sha1(td).hexdigest() != f[1]
            d = hashlib.sha256(td).digest()
        p = int(f[0]); rep[p] = hashlib.sha256(rep[p] + d).digest()
    fails += bad
    print(f'   IMA log: {n} entries, SHA-1 reconstruction mismatches {bad}')
    for p in (10, 11, 12):
        m = rep[p] == pcr[p]; fails += not m
        print(f'   PCR {p}: replay {"equals" if m else "DIFFERS FROM"} the quoted value')
print('ALL CHECKS PASSED' if fails == 0 else f'FAILED: {fails}')
sys.exit(1 if fails else 0)
