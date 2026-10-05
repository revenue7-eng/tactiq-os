#!/usr/bin/env python3
"""Offline check of the 2026-10-02 development-loader quote pair.

Run from this directory with tpm2-tools on PATH:
    python3 check.py
It verifies both quotes under ak.pub with their qualifying data, reads
the clock, resetCount and the PCR selection from the signed TPMS_ATTEST,
checks that the .pcr file carries exactly the selected values and zeros
everywhere else, ties each log to its quote through boot_aggregate, and
replays the IMA logs into PCR 10, 11 and 12. The logs were copied from
ascii_runtime_measurements, which carries SHA-1 template hashes; the
template data is rebuilt from the fields, checked against that SHA-1 for
every entry, and its SHA-256 is extended into the SHA-256 bank.

Exit status: 0 when every check passed, 1 when any check failed, 2 when
none failed but at least one could not run (for example tpm2_checkquote
missing). A check that could not run is never counted as passed.
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
    return extra, clock, reset, restart, sel

def pcr_values(path, sel):
    # tpm2_quote -o writes a TPML_PCR_SELECTION (UINT32 count, sixteen 8-byte
    # entries: UINT16 hash, UINT8 sizeofSelect, 4 select bytes, 1 pad), a
    # UINT32 count of digest lists, then that many TPML_DIGEST structs
    # (UINT32 count and eight TPM2B_DIGEST slots of 2 + 64 bytes),
    # little-endian. Values follow the selection order. The file is rebuilt
    # from what was parsed and compared byte for byte, so any nonzero byte in
    # padding or in an unused slot is reported as a layout error.
    b = open(path, 'rb').read(); vals = []; errs = []
    if len(b) < 136:
        return {}, ['file shorter than the selection header']
    cnt = struct.unpack('<I', b[0:4])[0]
    if not 1 <= cnt <= 16:
        return {}, [f'selection count {cnt}']
    head = struct.pack('<I', cnt); fsel = []
    for e in range(cnt):
        h, sz = struct.unpack('<HB', b[4 + 8 * e:7 + 8 * e])
        bits = b[7 + 8 * e:7 + 8 * e + min(sz, 4)]
        head += struct.pack('<HB', h, sz) + bits.ljust(4, b'\0') + b'\0'
        fsel += [i * 8 + j for i in range(len(bits)) for j in range(8) if bits[i] >> j & 1]
    head = head.ljust(132, b'\0')
    if b[:132] != head:
        errs.append('selection header has nonzero padding')
    if fsel != sel:
        errs.append('selection in the .pcr file differs from the signed one')
    lists = struct.unpack('<I', b[132:136])[0]
    if len(b) != 136 + 532 * lists:
        return {}, errs + [f'file length {len(b)} for {lists} digest lists']
    for i in range(lists):
        o = 136 + 532 * i
        n = struct.unpack('<I', b[o:o + 4])[0]
        if n > 8:
            errs.append(f'digest list {i} count {n}'); n = 8
        for k in range(8):
            q = o + 4 + 66 * k
            size = struct.unpack('<H', b[q:q + 2])[0]
            if k < n:
                if size != 32 or any(b[q + 2 + size:q + 66]):
                    errs.append(f'digest list {i} slot {k}: size {size} or nonzero padding')
                vals.append(b[q + 2:q + 2 + size])
            elif any(b[q:q + 66]):
                errs.append(f'digest list {i} unused slot {k} is not zero')
    if len(vals) != len(sel):
        errs.append(f'{len(vals)} values for {len(sel)} selected PCRs')
    return dict(zip(sel, vals)), errs

fails = 0; notrun = 0; clocks = {}; verified = {}
for s in ('cold', 'warm'):
    extra, clock, reset, restart, sel = attest(f'{s}.msg')
    try:
        r = subprocess.run(['tpm2_checkquote', '-u', 'ak.pub', '-m', f'{s}.msg',
                            '-s', f'{s}.sig', '-f', f'{s}.pcr', '-g', 'sha256',
                            '-q', extra.hex()], capture_output=True, text=True)
        ok = r.returncode == 0; state = 'verifies' if ok else 'FAILS'
        fails += not ok
    except OSError as e:
        ok = False; state = f'NOT CHECKED ({e.strerror}: tpm2_checkquote)'
        notrun += 1
    verified[s] = ok; clocks[s] = clock
    print(f'{s}: quote {state} under ak.pub, '
          f'qualifying data {extra.decode()!r}, clock {clock} ms, resetCount {reset}, '
          f'restartCount {restart}, PCRs {sel[0]}-{sel[-1]}')
    pcr, errs = pcr_values(f'{s}.pcr', sel)
    fails += len(errs)
    print(f'   .pcr layout: {"exact, zeros outside the values" if not errs else "; ".join(errs)}')
    if errs:
        continue
    agg = hashlib.sha256(b''.join(pcr[i] for i in range(10))).hexdigest()
    first = open(f'{s}.ima.log').readline().split()
    tied = len(first) > 4 and first[4] == 'boot_aggregate' and first[3] == 'sha256:' + agg
    fails += not tied
    print(f'   boot_aggregate {"equals" if tied else "DIFFERS FROM"} sha256 of the quoted PCR 0-9')
    rep = {10: bytes(32), 11: bytes(32), 12: bytes(32)}; bad = 0; n = 0
    per = {10: 0, 11: 0, 12: 0}
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
        p = int(f[0]); rep[p] = hashlib.sha256(rep[p] + d).digest(); per[p] += 1
    fails += bad
    print(f'   IMA log: {n} entries, SHA-1 reconstruction mismatches {bad}')
    for p in (10, 11, 12):
        m = rep[p] == pcr[p]; fails += not m
        print(f'   PCR {p}: replay of {per[p]} entries {"equals" if m else "DIFFERS FROM"} the quoted value')
if verified.get('cold') and verified.get('warm'):
    print(f'order: warm quote is {clocks["warm"] - clocks["cold"]} ms after cold '
          f'by the signed TPM clock')
else:
    print('order: NOT ESTABLISHED, both quotes must verify first')
if fails:
    print(f'FAILED: {fails}'); sys.exit(1)
if notrun:
    print(f'NOT ESTABLISHED: {notrun} check(s) could not run, none failed'); sys.exit(2)
print('ALL CHECKS PASSED'); sys.exit(0)
