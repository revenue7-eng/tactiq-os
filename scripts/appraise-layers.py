#!/usr/bin/env python3
"""appraise-layers.py: per-layer appraisal of one TPM quote, in the outcomes of
trace-spec section 3.1.5 (appraisal.platform_measurement).

For each PCR in the quote's signed selection it reports an outcome and, for a
layer that holds measurements, the routes the evidence offers for it:
  log        the layer's event log (TCG2 boot log, or the IMA log for PCR 10 to
             12) replays from the initial value to the quoted value
  reference  the layer's quoted value equals a value that a signed Reference
             Integrity Manifest (RIM) lists for it
The two routes establish different things. A log shows what ran, step by step,
with or without a reference. A reference shows that what ran is what the RIM
names, without the steps. Both are reported when both hold.

--definition chooses which routes establish a layer:
  rats        (default) log or reference. RFC 9334 describes appraisal as
              comparing Evidence against Reference Values from a Reference Value
              Provider under the Verifier's appraisal policy; an event log is
              one kind of Evidence, not a precondition.
  trace-text  log only. This is section 3.1.5 as its text reads at trace-spec
              main 4c7d6ec ("its event log replays from the initial value to
              the quoted value"); use it where a record must follow that text.

Outcomes, kept to what the evidence shows:
  - reset value, or one EV_SEPARATOR and nothing else:
      not-established / layer-not-measured
  - a log for the layer that does not replay to the quoted value:
      not-established / evidence-spans-multiple-boots (section 3.1.5 rule 3),
      also when the value matches the RIM: the evidence disagrees with itself
  - a route that counts under --definition: established, or under
      --policy appraised measured-not-appraised, because nothing in this
      evidence shows that what ran was appraised before it ran (rule 4)
  - no route that counts: left unlisted, which rule 1 reads as not established

The RIM is accepted only when its CMS signature verifies to --root and its
signer carries the RIM Signer EKU. Whether to trust --root is the relying
party's decision, not this script's.

Without --pcr the individual PCR values are not in the evidence. They are known
only when the signed pcrDigest equals a composite the RIM allows; each value then
equals its RIM value. Per-layer matching accepts any value the RIM lists for a
PCR and does not check that values of different slots are not mixed; the
composite comparison does.

Usage:
  appraise-layers.py --ak ak.pub --attest Q.attest --sig Q.sig
      [--pcr Q.pcr] [--qualifying-hex HEX | --qualifying-sha256-of FILE]
      [--bios-log FILE] [--ima-log FILE]
      [--rim rim.json --rim-p7s rim.json.p7s --root root.pem]
      [--require pcr:0,pcr:4=both,pcr:10=log,...] [--definition rats|trace-text]
      [--policy what-ran|appraised] [--json OUT]

--require lists the layers the relying party needs established. A layer may name
the route it needs: pcr:N=log, pcr:N=reference, or pcr:N=both (log and
reference). Without a route, any route that counts under --definition will do.
The routes are written beside the section 3.1.5 block, under "routes", and not
inside it: section 3.1.5 gives a layer an outcome and a reason and nothing else.

Exit: 0 nothing failed and every required layer is established;
      1 a check failed (signature, qualifying data, RIM, malformed input);
      2 nothing failed, but a required layer is not established.
Needs Python 3 (standard library), tpm2_checkquote (tpm2-tools), and openssl
with --rim.
"""
import argparse, hashlib, itertools, json, struct, subprocess, sys

ZERO = bytes(32)
SEPARATORS = {hashlib.sha256(ZERO + hashlib.sha256(e).digest()).digest()
              for e in (b'\xff' * 4, b'\x00' * 4)}
RIM_SIGNER_EKU = '2.25.209288284150790823604684143005475146259'
REASONS = ('layer-not-measured', 'measured-not-appraised', 'evidence-spans-multiple-boots')


class Failed(Exception):
    pass


def parse_attest(b):
    o = 6
    o += 2 + struct.unpack('>H', b[o:o + 2])[0]
    n = struct.unpack('>H', b[o:o + 2])[0]; extra = b[o + 2:o + 2 + n]; o += 2 + n
    clock, reset, restart, _safe = struct.unpack('>QIIB', b[o:o + 17]); o += 17
    fw = struct.unpack('>Q', b[o:o + 8])[0]; o += 8
    cnt = struct.unpack('>I', b[o:o + 4])[0]; o += 4; sel = []
    for _ in range(cnt):
        alg, sz = struct.unpack('>HB', b[o:o + 3]); o += 3
        bits = b[o:o + sz]; o += sz
        if alg == 0x000B:
            sel += [i * 8 + j for i in range(sz) for j in range(8) if bits[i] >> j & 1]
    dl = struct.unpack('>H', b[o:o + 2])[0]
    return dict(extra=extra, clock=clock, reset=reset, restart=restart,
                firmware=fw, sel=sel, pcr_digest=b[o + 2:o + 2 + dl])


def pcr_file(b, sel):
    vals = []
    lists = struct.unpack('<I', b[132:136])[0]
    for i in range(lists):
        o = 136 + 532 * i
        for k in range(struct.unpack('<I', b[o:o + 4])[0]):
            q = o + 4 + 66 * k
            size = struct.unpack('<H', b[q:q + 2])[0]
            vals.append(b[q + 2:q + 2 + size])
    if len(vals) != len(sel):
        raise Failed('the .pcr file does not carry the signed selection')
    return dict(zip(sel, vals))


def replay_tcg2(b):
    o = 8 + 20
    size = struct.unpack('<I', b[o:o + 4])[0]; o += 4
    spec = b[o:o + size]; o += size
    if struct.unpack('<I', b[4:8])[0] != 3 or not spec.startswith(b'Spec ID Event03'):
        raise Failed('boot log: first event is not a Spec ID Event03')
    n = struct.unpack('<I', spec[24:28])[0]
    sizes = dict(struct.unpack('<HH', spec[28 + 4 * i:32 + 4 * i]) for i in range(n))
    if 0x000B not in sizes:
        raise Failed('boot log: no SHA-256 bank')
    rep = {}
    while o < len(b):
        pcr, _t, c = struct.unpack('<III', b[o:o + 12]); o += 12
        dg = {}
        for _ in range(c):
            a = struct.unpack('<H', b[o:o + 2])[0]; o += 2
            dg[a] = b[o:o + sizes[a]]; o += sizes[a]
        o += 4 + struct.unpack('<I', b[o:o + 4])[0]
        rep[pcr] = hashlib.sha256(rep.get(pcr, ZERO) + dg[0x000B]).digest()
    if o != len(b):
        raise Failed('boot log: does not end on an event boundary')
    return rep


def replay_ima(text):
    rep = {}
    for line in text.splitlines():
        f = line.split()
        if not f:
            continue
        alg, dig = f[3].split(':', 1)
        parts = (alg.encode() + b':\0' + bytes.fromhex(dig), f[4].encode() + b'\0',
                 bytes.fromhex(f[5]) if len(f) > 5 else b'')
        td = b''.join(struct.pack('<I', len(x)) + x for x in parts)
        if f[1] == '0' * 40:
            d = b'\xff' * 32
        else:
            if hashlib.sha1(td).hexdigest() != f[1]:
                raise Failed('IMA log: template hash mismatch')
            d = hashlib.sha256(td).digest()
        p = int(f[0])
        rep[p] = hashlib.sha256(rep.get(p, ZERO) + d).digest()
    return rep


def rim_values(a):
    out = subprocess.run(
        ['openssl', 'cms', '-verify', '-binary', '-inform', 'DER', '-in', a.rim_p7s,
         '-content', a.rim, '-CAfile', a.root, '-purpose', 'any',
         '-signer', '/dev/stdout', '-out', '/dev/null'],
        capture_output=True, text=True)
    if 'CMS Verification successful' not in out.stderr + out.stdout:
        raise Failed('RIM: CMS signature does not verify to --root')
    signer = out.stdout[out.stdout.find('-----BEGIN'):]
    eku = subprocess.run(['openssl', 'x509', '-noout', '-ext', 'extendedKeyUsage'],
                         input=signer, capture_output=True, text=True).stdout
    if RIM_SIGNER_EKU not in eku:
        raise Failed('RIM: signer is not a RIM Signer (EKU)')
    p = json.load(open(a.rim))['pcr']
    vals = {}
    for i in p['selection']:
        v = p['values'][str(i)]
        vals[i] = [bytes.fromhex(x) for x in (v.values() if isinstance(v, dict) else v)]
    return p['selection'], vals


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--ak', required=True)
    ap.add_argument('--attest', required=True)
    ap.add_argument('--sig', required=True)
    ap.add_argument('--pcr')
    g = ap.add_mutually_exclusive_group()
    g.add_argument('--qualifying-hex')
    g.add_argument('--qualifying-sha256-of')
    ap.add_argument('--bios-log')
    ap.add_argument('--ima-log')
    ap.add_argument('--rim'); ap.add_argument('--rim-p7s'); ap.add_argument('--root')
    ap.add_argument('--require', default='')
    ap.add_argument('--definition', choices=('rats', 'trace-text'), default='rats')
    ap.add_argument('--policy', choices=('what-ran', 'appraised'), default='what-ran')
    ap.add_argument('--json')
    a = ap.parse_args()
    required = {}
    for item in (x for x in a.require.split(',') if x):
        key, _, need = item.partition('=')
        if need not in ('', 'log', 'reference', 'both'):
            raise Failed(f'--require {item}: the route is log, reference or both')
        required[key] = need
    lines = []

    q = parse_attest(open(a.attest, 'rb').read())
    if a.qualifying_hex is not None and q['extra'] != bytes.fromhex(a.qualifying_hex):
        raise Failed('qualifying data is not the expected value')
    if a.qualifying_sha256_of and q['extra'] != hashlib.sha256(
            open(a.qualifying_sha256_of, 'rb').read()).digest():
        raise Failed('qualifying data is not the sha256 of ' + a.qualifying_sha256_of)
    cmd = ['tpm2_checkquote', '-u', a.ak, '-m', a.attest, '-s', a.sig, '-g', 'sha256',
           '-q', q['extra'].hex()] + (['-f', a.pcr] if a.pcr else [])
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise Failed('quote does not verify under ' + a.ak)
    lines.append(f'quote verifies under {a.ak}; resetCount {q["reset"]}, '
                 f'PCRs {",".join(map(str, q["sel"]))}')

    sel = q['sel']
    values = pcr_file(open(a.pcr, 'rb').read(), sel) if a.pcr else None
    if values is not None and hashlib.sha256(
            b''.join(values[i] for i in sel)).digest() != q['pcr_digest']:
        raise Failed('PCR values do not reproduce the signed pcrDigest')

    ref = None
    if a.rim:
        if not (a.rim_p7s and a.root):
            raise Failed('--rim needs --rim-p7s and --root')
        rsel, ref = rim_values(a)
        lines.append('RIM signature verifies to --root, signer is a RIM Signer')
        if values is None:
            if rsel != sel:
                lines.append('RIM selection differs from the quote; values stay unknown')
            else:
                for combo in itertools.product(*(ref[i] for i in sel)):
                    if hashlib.sha256(b''.join(combo)).digest() == q['pcr_digest']:
                        values = dict(zip(sel, combo))
                        lines.append('pcrDigest equals a composite the RIM allows: '
                                     'each PCR equals its RIM value')
                        break
                else:
                    lines.append('pcrDigest equals no composite the RIM allows; '
                                 'individual PCR values are not known')

    logrep = {}
    if a.bios_log:
        logrep.update(replay_tcg2(open(a.bios_log, 'rb').read()))
    if a.ima_log:
        logrep.update({p: v for p, v in replay_ima(open(a.ima_log).read()).items() if p >= 10})

    layers, routes = {}, {}
    for i in sel:
        key = f'pcr:{i}'
        v = None if values is None else values[i]
        if v is not None and (v == ZERO or v in SEPARATORS):
            layers[key] = {'outcome': 'not-established', 'reason': 'layer-not-measured'}
            routes[key] = []
            continue
        rt = []
        if v is not None and i in logrep:
            if logrep[i] == v:
                rt.append('log')
            else:
                layers[key] = {'outcome': 'not-established',
                               'reason': 'evidence-spans-multiple-boots'}
        if v is not None and ref is not None and i in ref and v in ref[i]:
            rt.append('reference')
        routes[key] = rt
        if key in layers:
            continue
        counts = 'log' in rt or (a.definition == 'rats' and 'reference' in rt)
        if counts:
            layers[key] = ({'outcome': 'established'} if a.policy == 'what-ran' else
                           {'outcome': 'not-established', 'reason': 'measured-not-appraised'})

    def short(k):
        if layers.get(k, {}).get('outcome') != 'established':
            return True
        need, rt = required[k], routes.get(k, [])
        return (need == 'log' and 'log' not in rt or
                need == 'reference' and 'reference' not in rt or
                need == 'both' and not ('log' in rt and 'reference' in rt))
    missing = [k + (f'={required[k]}' if required[k] else '') for k in required if short(k)]
    for i in sel:
        k = f'pcr:{i}'
        o = layers.get(k)
        state = ('unlisted (not established)' if o is None else
                 o['outcome'] if o['outcome'] == 'established' else
                 'not-established / ' + o['reason'])
        via = f' [routes: {", ".join(routes[k])}]' if routes.get(k) else ''
        req = ('' if k not in required else
               f'  REQUIRED{" (" + required[k] + ")" if required[k] else ""}')
        lines.append(f'{k}: {state}{via}{req}')
    block = None if not layers else {'measurement': 'sha256:' + hashlib.sha256(
                 b''.join(values[i] for i in sel)).hexdigest(),
             'layers': layers}
    out = {'definition': a.definition, 'policy': a.policy,
           'platform_measurement': block, 'routes': routes, 'required_not_established': missing}
    if a.json:
        json.dump(out, open(a.json, 'w'), indent=1)
    print('\n'.join(lines))
    if missing:
        print('REQUIRED LAYERS NOT ESTABLISHED: ' + ', '.join(missing))
        return 2
    print('every required layer is established' if required else 'no layers required')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (Failed, OSError, ValueError, KeyError, struct.error) as e:
        print(f'FAILED: {e}')
        sys.exit(1)
