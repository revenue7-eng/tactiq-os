#!/usr/bin/env python3
"""Offline check of the 2026-10-15 development-image quote over PCR 0 to 12.

Run from this directory with tpm2-tools on PATH:
    python3 check.py
It verifies the quote under ak.pub with its qualifying data, checks that the
qualifying data is the RFC 7638 thumbprint of the Ed25519 key named below,
reads the clock, resetCount and PCR selection from the signed TPMS_ATTEST,
checks that quote.pcr carries exactly the selected values and zeros
everywhere else and that they reproduce the signed pcrDigest, replays the
SHA-256 bank of the boot event log (TCG2 crypto-agile) into PCR 0 to 9, ties
the IMA log to the quote through boot_aggregate, and replays the IMA log into
PCR 10, 11 and 12. The IMA log was copied from ascii_runtime_measurements,
which carries SHA-1 template hashes; the template data is rebuilt from the
fields, checked against that SHA-1 for every entry, and its SHA-256 is
extended into the SHA-256 bank.

Exit status: 0 when every check passed, 1 when any check failed, 2 when
none failed but at least one could not run (for example tpm2_checkquote
missing). A check that could not run is never counted as passed.
"""
import base64, hashlib, json, struct, subprocess, sys

# Ed25519 public key whose thumbprint is the quote's qualifying data.
WORKLOAD_X = '17aa9dffa8c80335dd534317985569523523e0633a600b93775e5d0b60d18930'
ZERO = bytes(32)

def thumbprint(x_hex):
    x = base64.urlsafe_b64encode(bytes.fromhex(x_hex)).rstrip(b'=').decode()
    jwk = json.dumps({'crv': 'Ed25519', 'kty': 'OKP', 'x': x},
                     separators=(',', ':'), sort_keys=True).encode()
    return hashlib.sha256(jwk).digest()

def attest(path):
    b = open(path, 'rb').read(); o = 6
    o += 2 + struct.unpack('>H', b[o:o + 2])[0]
    n = struct.unpack('>H', b[o:o + 2])[0]; extra = b[o + 2:o + 2 + n]; o += 2 + n
    clock, reset, restart, safe = struct.unpack('>QIIB', b[o:o + 17]); o += 17
    firmware = struct.unpack('>Q', b[o:o + 8])[0]; o += 8
    cnt = struct.unpack('>I', b[o:o + 4])[0]; o += 4; sel = []
    for _ in range(cnt):
        alg, sz = struct.unpack('>HB', b[o:o + 3]); o += 3
        bits = b[o:o + sz]; o += sz
        sel += [i * 8 + j for i in range(sz) for j in range(8) if bits[i] >> j & 1]
    dlen = struct.unpack('>H', b[o:o + 2])[0]
    return extra, clock, reset, restart, firmware, sel, b[o + 2:o + 2 + dlen]

def pcr_values(path, sel):
    # Same layout check as measurements/tpm-quotes-dev-20261002/check.py.
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
        errs.append('selection in quote.pcr differs from the signed one')
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

def replay_tcg2(path):
    """Replay the SHA-256 bank of a TCG PC Client crypto-agile event log."""
    b = open(path, 'rb').read(); o = 0
    pcr, etype = struct.unpack('<II', b[0:8]); o = 8 + 20
    size = struct.unpack('<I', b[o:o + 4])[0]; o += 4
    spec = b[o:o + size]; o += size
    if etype != 3 or not spec.startswith(b'Spec ID Event03'):
        raise ValueError('first event is not a Spec ID Event03')
    n = struct.unpack('<I', spec[24:28])[0]
    sizes = dict(struct.unpack('<HH', spec[28 + 4 * i:32 + 4 * i]) for i in range(n))
    if 0x000B not in sizes:
        raise ValueError('log has no SHA-256 bank')
    rep = {}; count = {}; kinds = {}
    while o < len(b):
        pcr, etype, c = struct.unpack('<III', b[o:o + 12]); o += 12
        dg = {}
        for _ in range(c):
            alg = struct.unpack('<H', b[o:o + 2])[0]; o += 2
            dg[alg] = b[o:o + sizes[alg]]; o += sizes[alg]
        es = struct.unpack('<I', b[o:o + 4])[0]; o += 4 + es
        rep[pcr] = hashlib.sha256(rep.get(pcr, ZERO) + dg[0x000B]).digest()
        count[pcr] = count.get(pcr, 0) + 1
        kinds.setdefault(pcr, set()).add(etype)
    if o != len(b):
        raise ValueError('log does not end on an event boundary')
    return rep, count, kinds

def tdata(f):
    alg, dig = f[3].split(':', 1)
    parts = (alg.encode() + b':\0' + bytes.fromhex(dig),
             f[4].encode() + b'\0',
             bytes.fromhex(f[5]) if len(f) > 5 else b'')
    return b''.join(struct.pack('<I', len(x)) + x for x in parts)

fails = 0; notrun = 0
extra, clock, reset, restart, firmware, sel, pcr_digest = attest('quote.msg')
try:
    r = subprocess.run(['tpm2_checkquote', '-u', 'ak.pub', '-m', 'quote.msg',
                        '-s', 'quote.sig', '-f', 'quote.pcr', '-g', 'sha256',
                        '-q', extra.hex()], capture_output=True, text=True)
    state = 'verifies' if r.returncode == 0 else 'FAILS'
    fails += r.returncode != 0
except OSError as e:
    state = f'NOT CHECKED ({e.strerror}: tpm2_checkquote)'; notrun += 1
print(f'quote {state} under ak.pub, clock {clock} ms, resetCount {reset}, '
      f'restartCount {restart}, firmware {firmware:016x}, PCRs {sel[0]}-{sel[-1]}')
bound = extra == thumbprint(WORKLOAD_X)
fails += not bound
print(f'qualifying data {extra.hex()} '
      f'{"equals" if bound else "DIFFERS FROM"} the RFC 7638 thumbprint of the named key')

pcr, errs = pcr_values('quote.pcr', sel)
fails += len(errs)
print(f'quote.pcr layout: {"exact, zeros outside the values" if not errs else "; ".join(errs)}')
if errs:
    print(f'FAILED: {fails}'); sys.exit(1)
comp = hashlib.sha256(b''.join(pcr[i] for i in sel)).digest() == pcr_digest
fails += not comp
print(f'PCR values {"reproduce" if comp else "DO NOT REPRODUCE"} the signed pcrDigest')

try:
    rep, count, kinds = replay_tcg2('quote.bios.log')
    for i in range(10):
        if i not in rep:
            fails += 1; print(f'PCR {i}: NOT IN the boot event log'); continue
        m = rep[i] == pcr[i]; fails += not m
        what = ', separator only' if kinds[i] == {4} else ''
        print(f'PCR {i}: boot log replay of {count[i]} event(s){what} '
              f'{"equals" if m else "DIFFERS FROM"} the quoted value')
except (ValueError, KeyError, struct.error) as e:
    fails += 1; print(f'boot event log: FAILED to parse ({e})')

agg = hashlib.sha256(b''.join(pcr[i] for i in range(10))).hexdigest()
lines = [l.split() for l in open('quote.ima.log') if l.split()]
tied = lines and lines[0][4] == 'boot_aggregate' and lines[0][3] == 'sha256:' + agg
fails += not tied
print(f'boot_aggregate {"equals" if tied else "DIFFERS FROM"} sha256 of the quoted PCR 0-9')
irep = {10: ZERO, 11: ZERO, 12: ZERO}; per = {10: 0, 11: 0, 12: 0}; bad = 0
for f in lines:
    try:
        td = tdata(f)
    except (ValueError, IndexError):
        bad += 1; continue
    if f[1] == '0' * 40:
        d = b'\xff' * 32
    else:
        bad += hashlib.sha1(td).hexdigest() != f[1]
        d = hashlib.sha256(td).digest()
    p = int(f[0]); irep[p] = hashlib.sha256(irep[p] + d).digest(); per[p] += 1
fails += bad
print(f'IMA log: {len(lines)} entries, SHA-1 reconstruction mismatches {bad}')
for p in (10, 11, 12):
    m = irep[p] == pcr[p]; fails += not m
    print(f'PCR {p}: IMA replay of {per[p]} entry(ies) {"equals" if m else "DIFFERS FROM"} the quoted value')
akd = 'sha256:' + hashlib.sha256(open('ak.pub', 'rb').read()).hexdigest()
ak_in_log = any(f[4] == '/data/tactiq/keys/ak.pub' and f[3] == akd for f in lines)
fails += not ak_in_log
print(f'IMA entry for /data/tactiq/keys/ak.pub {"equals" if ak_in_log else "DOES NOT EQUAL"} sha256 of ak.pub')

if fails:
    print(f'FAILED: {fails}'); sys.exit(1)
if notrun:
    print(f'NOT ESTABLISHED: {notrun} check(s) could not run, none failed'); sys.exit(2)
print('ALL CHECKS PASSED'); sys.exit(0)
