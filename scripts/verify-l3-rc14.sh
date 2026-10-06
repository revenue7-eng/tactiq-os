#!/usr/bin/env bash
# verify-l3-rc14.sh: runs the checks of VERIFY-L3-rc14.md for TactiQ OS
# v2.1.0-rc14 and prints one of three results per check:
#   PASS             the expected value is met
#   FAIL             the check ran and the value is wrong
#   NOT ESTABLISHED  the evidence cannot answer this; the line says why
# A NOT ESTABLISHED line is never a pass and never a failure.
#
# Exit codes: 0 nothing failed and the boot state matched the reference;
#             1 at least one check failed;
#             2 nothing failed, but the boot state was not established.
#
# VERIFY-L3-rc14.md is the authoritative procedure. This script is a
# convenience that follows it; every expected value below is written on
# that page, so read the script before trusting its output.
#
# Lineage: verify-l3-rc13.sh v1 to v5 (rc13 release and errata). This script
# keeps every check of v5, including its handling of certificates outside
# their validity dates, and changes the following.
#
# The evidence archive and this script are listed in the release's
# SHA256SUMS, which the release workflow signs with Sigstore. The archive
# hash is therefore no longer a constant in the script: the script checks
# that the archive, the RIM and the script itself match their lines in
# SHA256SUMS. It does not check the Sigstore signature over SHA256SUMS;
# scripts/verify-release.sh does, and a NOT ESTABLISHED line says so.
#
# The archive carries its own SHA256SUMS signed by the TactiQ OS Release
# Evidence Signer (CMS detached, SHA256SUMS.p7s), a leaf of the offline
# release hierarchy whose only extended key usage is the evidence purpose.
# The Sigstore signature rests on the repository's release workflow; this one
# rests on the release root. Step 1a checks it, with the time labelling of
# v5.
#
# The registration record and the quotes are found in the archive instead of
# being named here; an archive with no quote or with other than one record
# fails. The reference for the boot state is computed from the signed RIM
# over the PCR selection the RIM names, for every slot it describes and every
# value it lists for a PCR; v5 compared against a constant for slot A.
#
# Step 8 printing nothing is a failure (rc13 errata, section 2): v1 to v5
# dropped its NOT ESTABLISHED lines silently when the fragment raised.
#
# Needs: bash, curl, OpenSSL 3.x, Python 3 (standard library), sha256sum,
# tpm2-tools (tpm2_checkquote, tpm2_print). No TPM is needed.
#
# Usage: verify-l3-rc14.sh [dir]
#   Without an argument the files are downloaded from the v2.1.0-rc14
#   release. With a directory, the files are read from it instead:
#   release-root-r2.pem, rim-rock5a.json, rim-rock5a.json.p7s, SHA256SUMS,
#   l3-evidence-rc14.tar.gz.
set -u
TAG=v2.1.0-rc14
ARCH=l3-evidence-rc14
ROOT_FP="8E:10:04:1E:BB:FC:CB:A0:36:62:1B:2E:45:36:87:D2:9A:50:D7:15:65:F2:99:CB:41:28:B4:CE:B9:65:FF:E8"
EV_EKU="X509v3ExtendedKeyUsage:critical2.25.303991386130890852620485224389791976682"
SRC="${1:-}"
if [ -n "$SRC" ]; then SRC=$(cd "$SRC" 2>/dev/null && pwd) || { echo "no such directory: $1"; exit 1; }; fi
SELF=$(sha256sum "$0" 2>/dev/null | cut -d' ' -f1)
REL=https://github.com/revenue7-eng/tactiq-os/releases/download/$TAG
W=$(mktemp -d) || exit 1
cd "$W" || exit 1
echo "working directory: $W"
echo "run (UTC):         $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "script sha256:     $SELF"
echo "openssl:           $(openssl version 2>&1)"
echo "tpm2-tools:        $(tpm2_checkquote --version 2>&1 | head -n 1)"
echo "python:            $(python3 --version 2>&1)"
fails=0; passes=0; nest=0; boot_ne=0; infineon_local=0; rootok=0
ok()  { echo "PASS             $1"; passes=$((passes+1)); }
bad() { echo "FAIL             $1"; fails=$((fails+1)); }
ne()  { echo "NOT ESTABLISHED  $1"; nest=$((nest+1)); }
why() { printf '%s\n' "$1" | grep -i -m 1 'error\|not found\|cannot' || printf '%s\n' "$1" | tail -n 1; }
tlabel() { case "$1" in *"has expired"*) echo "certificate expired";; *"not yet valid"*) echo "certificate not yet valid";; *) echo "certificate outside its validity dates";; esac; }
TIMENOTE="the signature and chain verify to the release root when validity dates are ignored; nothing in these files shows the signature was made while the certificate was valid"
chk() { if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 (got: $2)"; fi; }
listed() { awk -v f="$2" '$2==f {print $1}' "$1" | head -n 1; }

echo "== files"
FILES="release-root-r2.pem rim-rock5a.json rim-rock5a.json.p7s SHA256SUMS $ARCH.tar.gz"
if [ -n "$SRC" ]; then
  got=1; for f in $FILES; do cp "$SRC/$f" . || got=0; done
  [ "$got" -eq 1 ] && ok "files copied from $SRC" || { bad "files copy from $SRC"; exit 1; }
else
  got=1; for f in $FILES; do curl -sSfL -m 120 -o "$f" "$REL/$f" || got=0; done
  [ "$got" -eq 1 ] && ok "files downloaded from the $TAG release" || { bad "download from $REL"; exit 1; }
fi
for f in "$ARCH.tar.gz" rim-rock5a.json rim-rock5a.json.p7s; do
  l=$(listed SHA256SUMS "$f")
  if [ -z "$l" ]; then bad "$f is not listed in the release SHA256SUMS"
  else chk "$f matches the release SHA256SUMS" "$(sha256sum "$f" | cut -d' ' -f1)" "$l"; fi
done
l=$(listed SHA256SUMS "verify-l3-rc14.sh")
if [ -z "$l" ]; then bad "verify-l3-rc14.sh is not listed in the release SHA256SUMS"
else chk "this script is the one listed in the release SHA256SUMS" "$SELF" "$l"; fi
ne "Sigstore signature over the release SHA256SUMS: not checked by this script; scripts/verify-release.sh --tag $TAG checks it, and every line above rests on it"
tar -xzf "$ARCH.tar.gz" || { bad "cannot unpack the evidence archive"; exit 1; }
mv release-root-r2.pem rim-rock5a.json rim-rock5a.json.p7s "$ARCH/"
cd "$ARCH" || exit 1
if sha256sum -c --quiet SHA256SUMS; then ok "archive SHA256SUMS"; else bad "archive SHA256SUMS"; fi

echo "== step 1: release root"
fp=$(openssl x509 -in release-root-r2.pem -noout -fingerprint -sha256 | cut -d= -f2)
chk "root fingerprint" "$fp" "$ROOT_FP"
[ "$fp" = "$ROOT_FP" ] && rootok=1

echo "== step 1a: evidence list signature"
rm -f ev-out.pem
out=$(openssl cms -verify -binary -inform DER -in SHA256SUMS.p7s -content SHA256SUMS -CAfile release-root-r2.pem -certfile signing-ca.pem -purpose any -signer ev-out.pem -out /dev/null 2>&1)
if [ "$out" = "CMS Verification successful" ]; then ok "archive SHA256SUMS signature"
else
  out2=$(openssl cms -verify -no_check_time -binary -inform DER -in SHA256SUMS.p7s -content SHA256SUMS -CAfile release-root-r2.pem -certfile signing-ca.pem -purpose any -signer ev-out.pem -out /dev/null 2>&1)
  if [ "$rootok" -eq 1 ] && [ "$out2" = "CMS Verification successful" ]; then bad "archive SHA256SUMS signature: $(tlabel "$out"); $TIMENOTE"
  else rm -f ev-out.pem; r="$out2"; [ "$out2" = "CMS Verification successful" ] && r="$out"; bad "archive SHA256SUMS signature: does not verify or does not chain to the release root (got: $(why "$r"))"; fi
fi
if [ -s ev-out.pem ]; then
  chk "evidence signer EKU" "$(openssl x509 -in ev-out.pem -noout -ext extendedKeyUsage 2>/dev/null | tr -d ' \n')" "$EV_EKU"
else bad "evidence signer EKU: could not run, no signer was extracted because the signature did not verify"; fi

REG=""; nreg=0
for f in registration-*.json; do [ -e "$f" ] || continue; REG="$f"; nreg=$((nreg+1)); done
if [ "$nreg" -ne 1 ]; then bad "registration record: the archive holds $nreg records, expected exactly one"; REG=missing-registration.json; fi
QUOTES=$(ls *.attest 2>/dev/null | sed 's/\.attest$//' | sort)
LASTQ=$(printf '%s\n' $QUOTES | tail -n 1)
if [ -z "$QUOTES" ]; then bad "quotes: the archive holds none"; fi
for q in $QUOTES; do for x in msg sig; do [ -e "$q.$x" ] || bad "quote $q: $q.$x missing"; done; done
echo "INFO             registration record: $REG; quotes: $(echo $QUOTES)"

echo "== step 2: Registration Signer"
out=$(openssl verify -CAfile release-root-r2.pem -untrusted signing-ca.pem reg-signer.pem 2>&1)
if [ "$out" = "reg-signer.pem: OK" ]; then ok "leaf chain"
else
  out2=$(openssl verify -no_check_time -CAfile release-root-r2.pem -untrusted signing-ca.pem reg-signer.pem 2>&1)
  if [ "$rootok" -eq 1 ] && [ "$out2" = "reg-signer.pem: OK" ]; then bad "leaf chain: $(tlabel "$out"); the chain verifies to the release root when validity dates are ignored"
  else r="$out2"; [ "$out2" = "reg-signer.pem: OK" ] && r="$out"; bad "leaf chain: does not chain to the release root (got: $(why "$r"))"; fi
fi
eku=$(openssl x509 -in reg-signer.pem -noout -ext extendedKeyUsage | tr -d ' \n')
chk "leaf EKU" "$eku" "X509v3ExtendedKeyUsage:critical2.25.205994972697553183157730487844756597568"

echo "== step 3: record signature"
out=$(openssl cms -verify -binary -inform DER -in "$REG.p7s" -content "$REG" -CAfile release-root-r2.pem -certfile signing-ca.pem -purpose any -signer signer-out.pem -out /dev/null 2>&1)
if [ "$out" = "CMS Verification successful" ]; then ok "record CMS"
else
  out2=$(openssl cms -verify -no_check_time -binary -inform DER -in "$REG.p7s" -content "$REG" -CAfile release-root-r2.pem -certfile signing-ca.pem -purpose any -signer signer-out.pem -out /dev/null 2>&1)
  if [ "$rootok" -eq 1 ] && [ "$out2" = "CMS Verification successful" ]; then bad "record CMS: $(tlabel "$out"); $TIMENOTE"
  else rm -f signer-out.pem; r="$out2"; [ "$out2" = "CMS Verification successful" ] && r="$out"; bad "record CMS: signature does not verify or does not chain to the release root (got: $(why "$r"))"; fi
fi
if [ -s signer-out.pem ]; then
  a=$(openssl x509 -in signer-out.pem -noout -fingerprint -sha256)
  b=$(openssl x509 -in reg-signer.pem -noout -fingerprint -sha256)
  chk "record signer is the leaf" "$a" "$b"
else bad "record signer is the leaf: could not run, no signer was extracted because the record signature did not verify"; fi
ne "registration event: the record is TactiQ AI's signed statement that this AK was registered against this EK; that the registration happened as the record states is not established by these files"

echo "== step 4: EK chain and record contents"
if curl -sSf -m 30 -o mfr034.crt https://pki.infineon.com/OptigaRsaMfrCA034/OptigaRsaMfrCA034.crt \
   && curl -sSf -m 30 -o root.crt https://pki.infineon.com/OptigaRsaRootCA/OptigaRsaRootCA.crt \
   && openssl x509 -inform DER -in mfr034.crt -noout 2>/dev/null \
   && openssl x509 -inform DER -in root.crt -noout 2>/dev/null; then
  ok "Infineon CAs downloaded from Infineon"
else
  echo "INFO             Infineon not reachable or did not return certificates, using the copies in the archive"
  cp infineon-mfr034.crt mfr034.crt; cp infineon-root.crt root.crt
  infineon_local=1
fi
openssl x509 -inform DER -in root.crt -out root.pem
openssl x509 -inform DER -in mfr034.crt -out mfr034.pem
openssl x509 -inform DER -in ek.der -out ek.pem
out=$(openssl verify -CAfile root.pem -untrusted mfr034.pem ek.pem 2>&1)
chk "EK chain" "$out" "ek.pem: OK"
fp=$(openssl x509 -in root.pem -noout -fingerprint -sha256 | cut -d= -f2)
chk "Infineon root fingerprint" "$fp" "89:9E:35:47:4C:98:07:EB:4C:7F:2F:7A:12:DA:00:28:FB:25:0C:D0:21:54:D0:00:9F:CA:7D:9C:66:57:4F:3B"
if [ "$infineon_local" -eq 1 ]; then
  ne "EK chain independent of TactiQ AI: the Infineon certificates came from the archive and the root fingerprint is compared with a value in this script; confirm $fp through a channel of your own"
fi
rs=$(python3 -c "import json; print(json.load(open('$REG'))['root_sha256'])")
im=$(python3 -c "import json,hashlib; print(hashlib.sha256(bytes.fromhex(json.load(open('$REG'))['intermediate_certificate'])).hexdigest())")
chk "issuing CA equals record" "$im" "$(sha256sum mfr034.crt | cut -d' ' -f1)"
chk "record root_sha256" "$rs" "$(echo "$fp" | tr -d ':' | tr 'A-F' 'a-f')"
rec=$(python3 -c "import json,hashlib; d=json.load(open('$REG')); print(hashlib.sha256(bytes.fromhex(d['ek_certificate'])).hexdigest(), hashlib.sha256(bytes.fromhex(d['ak_public'])).hexdigest())")
fil="$(sha256sum ek.der | cut -d' ' -f1) $(sha256sum ak.pub | cut -d' ' -f1)"
chk "ek.der and ak.pub are the signed ones" "$rec" "$fil"
rv=$(python3 -c "import json; print(json.load(open('$REG')).get('revocation_checked'))")
if [ "$rv" = "True" ]; then ok "EK revocation checked at registration"
else ne "EK certificate not revoked: record says revocation_checked=$rv"; fi

echo "== step 5: AK name"
n="000b$(tail -c +3 ak.pub | sha256sum | cut -d' ' -f1)"
rn=$(python3 -c "import json; print(json.load(open('$REG'))['ak_name'])")
chk "AK name equals record" "$n" "$rn"

echo "== step 6: quotes"
for q in $QUOTES; do
  out=$(tpm2_checkquote -u ak.pub -m $q.attest -s $q.sig -g sha256 -q "$(sha256sum $q.msg | cut -d' ' -f1)" 2>&1); rc=$?
  if [ "$rc" -eq 0 ]; then ok "quote $q"
  else bad "quote $q (tpm2_checkquote exit $rc: $(why "$out"))"; fi
done
cp "$LASTQ.msg" bad.msg
off=$(( $(stat -c %s bad.msg) / 2 )); c=$(dd if=bad.msg bs=1 skip=$off count=1 2>/dev/null); [ "$c" = "X" ] && c=Y || c=X
printf '%s' "$c" | dd of=bad.msg bs=1 seek=$off conv=notrunc 2>/dev/null
out=$(tpm2_checkquote -u ak.pub -m "$LASTQ.attest" -s "$LASTQ.sig" -g sha256 -q "$(sha256sum bad.msg | cut -d' ' -f1)" 2>&1); rc=$?
if [ "$rc" -ne 0 ] && case "$out" in *"Error validating nonce"*) true;; *) false;; esac; then ok "tampered record rejected"
else bad "tampered record not rejected for the expected reason (tpm2_checkquote exit $rc: $(why "$out"))"; fi
ne "origin of the TPM reset before this boot: resetCount is signed, but SPL drives the TPM reset line and the running system can drive it too, so a reset is not by itself evidence of a reboot (disclosure as corrected in revenue7-eng/tactiq-os#224; the rc13 RIM text on warm reboot is superseded; the RIM of this release carries the corrected text)"
ne "freshness: qualifying data is the hash of the agent's own record, not a challenge chosen by the reviewer"

echo "== step 7: boot state against the RIM"
out=$(openssl cms -verify -binary -inform DER -in rim-rock5a.json.p7s -content rim-rock5a.json -CAfile release-root-r2.pem -purpose any -signer rim-signer.pem -out /dev/null 2>&1)
rimok=0
if [ "$out" = "CMS Verification successful" ]; then ok "RIM CMS"; rimok=1
else
  out2=$(openssl cms -verify -no_check_time -binary -inform DER -in rim-rock5a.json.p7s -content rim-rock5a.json -CAfile release-root-r2.pem -purpose any -signer rim-signer.pem -out /dev/null 2>&1)
  if [ "$rootok" -eq 1 ] && [ "$out2" = "CMS Verification successful" ]; then bad "RIM CMS: $(tlabel "$out"); $TIMENOTE"
  else rm -f rim-signer.pem; r="$out2"; [ "$out2" = "CMS Verification successful" ] && r="$out"; bad "RIM CMS: signature does not verify or does not chain to the release root (got: $(why "$r"))"; fi
fi
if [ -s rim-signer.pem ]; then
  eku=$(openssl x509 -in rim-signer.pem -noout -ext extendedKeyUsage 2>/dev/null | tr -d ' \n')
  [ "$eku" = "X509v3ExtendedKeyUsage:critical2.25.209288284150790823604684143005475146259" ] || rimok=0
  chk "RIM signer EKU" "$eku" "X509v3ExtendedKeyUsage:critical2.25.209288284150790823604684143005475146259"
else bad "RIM signer EKU: could not run, no signer was extracted because the RIM signature did not verify"; fi
# every composite the RIM allows: per slot, and per listed value of a PCR
refs=$(python3 - <<'PY'
import json, hashlib, itertools
p = json.load(open('rim-rock5a.json'))['pcr']
sel, vals = p['selection'], p['values']
slots = sorted({k for i in sel if isinstance(vals[str(i)], dict) for k in vals[str(i)]}) or ['-']
for s in slots:
    opts = []
    for i in sel:
        v = vals[str(i)]
        opts.append([v[s]] if isinstance(v, dict) else list(v))
    for combo in itertools.product(*opts):
        print(s, hashlib.sha256(b''.join(bytes.fromhex(x) for x in combo)).hexdigest())
PY
)
if [ -z "$refs" ]; then bad "RIM reference: no composite could be computed from rim-rock5a.json"; rimok=0
else echo "INFO             reference composites from the RIM: $(echo "$refs" | wc -l) ($(echo "$refs" | awk '{print $1}' | sort -u | tr '\n' ' ')slots)"; fi
for q in $QUOTES; do
  if [ "$rimok" -ne 1 ]; then ne "boot state of quote $q: the reference did not verify, so there is nothing to compare against"; boot_ne=1; continue; fi
  pd=$(tpm2_print -t TPMS_ATTEST $q.attest 2>/dev/null | sed -n 's/.*pcrDigest: //p')
  slot=$(echo "$refs" | awk -v d="$pd" '$2==d {print $1; exit}')
  if [ -z "$pd" ]; then bad "boot state of quote $q: pcrDigest could not be read (tpm2_print)"
  elif [ -n "$slot" ]; then ok "pcrDigest $q matches the RIM (slot $slot)"
  else bad "boot state of quote $q: pcrDigest differs from every composite the RIM allows, so this boot is not the reference boot; why it differs is not established by this evidence"; fi
done

echo "== step 8: what the matching digest covers"
FIRSTQ=$(printf '%s\n' $QUOTES | head -n 1)
if [ "$rimok" -ne 1 ]; then s8="NOT ESTABLISHED  per-PCR coverage: the reference did not verify"; else
s8=$(python3 - "$PWD" "$FIRSTQ" <<'PY'
import hashlib, json, struct, sys, os
d, q = sys.argv[1], sys.argv[2]
h = lambda b: hashlib.sha256(b).digest()
z = bytes(32)
sep = {h(z + h(b'\x00' * 4)).hex(): "separator 0x00000000",
       h(z + h(b'\xff' * 4)).hex(): "separator 0xFFFFFFFF"}
rim = json.load(open(os.path.join(d, 'rim-rock5a.json')))['pcr']['values']
b = open(os.path.join(d, q + '.attest'), 'rb').read()
o = 6
o += 2 + struct.unpack('>H', b[o:o+2])[0]          # qualifiedSigner
o += 2 + struct.unpack('>H', b[o:o+2])[0]          # extraData
o += 17 + 8                                        # clockInfo, firmwareVersion
cnt = struct.unpack('>I', b[o:o+4])[0]; o += 4
sel = set()
for _ in range(cnt):
    alg, n = struct.unpack('>HB', b[o:o+3]); o += 3
    bits = b[o:o+n]; o += n
    if alg == 0x000b:
        sel |= {i * 8 + j for i in range(n) for j in range(8) if bits[i] >> j & 1}
for i in sorted(sel):
    v = rim[str(i)]
    vals = list(v.values()) if isinstance(v, dict) else v
    kinds = {sep.get(x, "zero" if x == '0' * 64 else "measured") for x in vals}
    if kinds == {"measured"}:
        print(f"PASS             PCR {i}: reference holds measurements")
    elif "zero" in kinds:
        print(f"NOT ESTABLISHED  PCR {i}: reference is the reset value, this layer was never extended")
    else:
        print(f"NOT ESTABLISHED  PCR {i}: reference holds a {', '.join(sorted(kinds))} only, nothing was measured at this layer; a match here confirms only that nothing was recorded")
out = [i for i in range(24) if i not in sel]
if out:
    print(f"NOT ESTABLISHED  PCR {out[0]} to {out[-1]}: not in the quote's selection, including PCR 10 (IMA) and PCR 11; nothing is shown about them")
PY
); fi
if [ -z "$s8" ]; then bad "per-PCR coverage: step 8 printed nothing, so its NOT ESTABLISHED lines are missing"
else
  echo "$s8"
  passes=$((passes + $(echo "$s8" | grep -c '^PASS')))
  nest=$((nest + $(echo "$s8" | grep -c '^NOT ESTABLISHED')))
fi
ne "files on the root filesystem: the PCR values cover the boot chain up to the kernel, its device tree and its command line; whether the root filesystem is verity-protected on a release device, and that IMA is off in the production image, are stated in the coverage manifest; this script does not check either"

echo
echo "PASS: $passes   FAIL: $fails   NOT ESTABLISHED: $nest"
# exit 0: nothing failed and the boot state matched the reference
# exit 1: at least one check failed
# exit 2: nothing failed, but the boot state was not established
if [ "$fails" -ne 0 ]; then echo "FAILED CHECKS: $fails"; exit 1
elif [ "$boot_ne" -ne 0 ]; then echo "BOOT STATE NOT ESTABLISHED. This is not a pass."; exit 2
else echo "NO CHECK FAILED. Read the NOT ESTABLISHED lines: they are not passes."; exit 0; fi
