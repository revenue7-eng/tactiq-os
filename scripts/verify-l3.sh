#!/usr/bin/env bash
# verify-l3.sh: checks the L3 evidence of a TactiQ OS release (or of a build
# signed under someone else's release root) and prints one of three results
# per check:
#   PASS             the expected value is met
#   FAIL             the check ran and the value is wrong
#   NOT ESTABLISHED  the evidence cannot answer this; the line says why
# A NOT ESTABLISHED line is never a pass and never a failure.
#
# Exit codes: 0 nothing failed and the boot state matched the reference;
#             1 at least one check failed;
#             2 nothing failed, but the boot state was not established.
#
# This is verify-l3-rc14-v2.sh with its constants turned into options. The
# checks and their wording are those of v2; what was fixed to our release is
# now a parameter whose default is our value:
#
#   --tag TAG            release tag (default v2.1.0-rc14)
#   --repo OWNER/REPO    repository whose release is downloaded
#                        (default revenue7-eng/tactiq-os)
#   --board NAME         the RIM is rim-NAME.json (default rock5a)
#   --root-file NAME     release root certificate file (default
#                        release-root-r2.pem)
#   --root-fp FP         expected SHA-256 fingerprint of that root, colon
#                        separated hex (default: the TactiQ OS release root)
#   --archive NAME       evidence archive, without .tar.gz (default
#                        l3-evidence-<the part of the tag after its last "-">)
#   --ek-root FILE       EK root CA certificate, DER or PEM, instead of the
#                        Infineon OPTIGA RSA root
#   --ek-intermediate FILE
#                        EK issuing CA certificate, DER or PEM; goes with
#                        --ek-root
#   --ek-root-fp FP      expected SHA-256 fingerprint of the EK root; without
#                        it a root given by --ek-root is reported NOT
#                        ESTABLISHED, since only the file pins it
#   --tpm-fw-min HEX     lowest accepted firmwareVersion of the TPM, as the
#                        64-bit value in the quote (default 0x0007005700000000,
#                        Infineon 7.87, applied only with the Infineon root);
#                        with another EK root and no value, step 6a is NOT
#                        ESTABLISHED
#   --dir DIR, or DIR    read the files from DIR instead of downloading them
#
# With no option the script checks the v2.1.0-rc14 release of
# revenue7-eng/tactiq-os exactly as verify-l3-rc14-v2.sh does; only the line
# about the script's own entry in the release SHA256SUMS differs.
#
# The scripts verify-l3-rc14.sh and verify-l3-rc14-v2.sh stay unchanged: the
# first is listed in the rc14 SHA256SUMS that Sigstore signs, the second in
# the rc14 errata. This file is a separate tool.
#
# The extended key usage values checked in steps 1a, 2 and 7 are the purpose
# OIDs that gen-pki.sh writes into the Evidence, Registration and RIM Signer
# leaves; a hierarchy made with gen-pki.sh under another root carries the same
# values.
#
# Needs: bash, curl, OpenSSL 3.x, Python 3 (standard library), sha256sum,
# tpm2-tools (tpm2_checkquote, tpm2_print). No TPM is needed.
set -u

TAG=v2.1.0-rc14
REPO=revenue7-eng/tactiq-os
BOARD=rock5a
ROOTF=release-root-r2.pem
ROOT_FP="8E:10:04:1E:BB:FC:CB:A0:36:62:1B:2E:45:36:87:D2:9A:50:D7:15:65:F2:99:CB:41:28:B4:CE:B9:65:FF:E8"
ARCH=""
EKROOT=""; EKINT=""; EKROOT_FP=""
TPM_FW_MIN=""
SRC=""
INFINEON_ROOT_FP="89:9E:35:47:4C:98:07:EB:4C:7F:2F:7A:12:DA:00:28:FB:25:0C:D0:21:54:D0:00:9F:CA:7D:9C:66:57:4F:3B"
INFINEON_FW_MIN=0x0007005700000000

usage() { sed -n '/^#   --tag/,/^#   --dir/p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }
need() { [ -n "${2:-}" ] || { echo "$1 needs a value" >&2; exit 2; }; }
while [ $# -gt 0 ]; do
  case "$1" in
    --tag) need "$1" "${2:-}"; TAG="$2"; shift 2 ;;
    --repo) need "$1" "${2:-}"; REPO="$2"; shift 2 ;;
    --board) need "$1" "${2:-}"; BOARD="$2"; shift 2 ;;
    --root-file) need "$1" "${2:-}"; ROOTF="$2"; shift 2 ;;
    --root-fp) need "$1" "${2:-}"; ROOT_FP=$(echo "$2" | tr 'a-f' 'A-F'); shift 2 ;;
    --archive) need "$1" "${2:-}"; ARCH="$2"; shift 2 ;;
    --ek-root) need "$1" "${2:-}"; EKROOT="$2"; shift 2 ;;
    --ek-intermediate) need "$1" "${2:-}"; EKINT="$2"; shift 2 ;;
    --ek-root-fp) need "$1" "${2:-}"; EKROOT_FP=$(echo "$2" | tr 'a-f' 'A-F'); shift 2 ;;
    --tpm-fw-min) need "$1" "${2:-}"; TPM_FW_MIN="$2"; shift 2 ;;
    --dir) need "$1" "${2:-}"; SRC="$2"; shift 2 ;;
    -h|--help) usage ;;
    -*) echo "unknown option: $1" >&2; usage ;;
    *) [ -z "$SRC" ] || usage; SRC="$1"; shift ;;
  esac
done
case "$BOARD" in *[!A-Za-z0-9._-]*|"") echo "--board: letters, digits, dot, dash, underscore only" >&2; exit 2 ;; esac
case "$ROOTF" in */*|"") echo "--root-file: a file name, not a path" >&2; exit 2 ;; esac
[ -n "$ARCH" ] || ARCH="l3-evidence-${TAG##*-}"
case "$ARCH" in */*) echo "--archive: a name, not a path" >&2; exit 2 ;; esac
if [ -n "$EKROOT" ] || [ -n "$EKINT" ]; then
  [ -n "$EKROOT" ] && [ -n "$EKINT" ] || { echo "--ek-root and --ek-intermediate go together" >&2; exit 2; }
  [ -r "$EKROOT" ] && [ -r "$EKINT" ] || { echo "cannot read --ek-root or --ek-intermediate" >&2; exit 2; }
  EKROOT=$(cd "$(dirname "$EKROOT")" && pwd)/$(basename "$EKROOT")
  EKINT=$(cd "$(dirname "$EKINT")" && pwd)/$(basename "$EKINT")
  INFINEON=0
else
  INFINEON=1; EKROOT_FP="$INFINEON_ROOT_FP"
  [ -n "$TPM_FW_MIN" ] || TPM_FW_MIN=$INFINEON_FW_MIN
fi
RIM="rim-$BOARD.json"
if [ -n "$SRC" ]; then SRC=$(cd "$SRC" 2>/dev/null && pwd) || { echo "no such directory: $SRC"; exit 1; }; fi
SELF=$(sha256sum "$0" 2>/dev/null | cut -d' ' -f1)
REL=https://github.com/$REPO/releases/download/$TAG
EV_EKU="X509v3ExtendedKeyUsage:critical2.25.303991386130890852620485224389791976682"
REG_EKU="X509v3ExtendedKeyUsage:critical2.25.205994972697553183157730487844756597568"
RIM_EKU="X509v3ExtendedKeyUsage:critical2.25.209288284150790823604684143005475146259"
W=$(mktemp -d) || exit 1
cd "$W" || exit 1
echo "working directory: $W"
echo "run (UTC):         $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "script sha256:     $SELF"
echo "release:           $REPO $TAG, board $BOARD, archive $ARCH, root file $ROOTF"
echo "release root:      $ROOT_FP"
if [ "$INFINEON" -eq 1 ]; then echo "EK root:           Infineon OPTIGA RSA root"
else echo "EK root:           $EKROOT, issuing CA $EKINT"; fi
echo "openssl:           $(openssl version 2>&1)"
echo "tpm2-tools:        $(tpm2_checkquote --version 2>&1 | head -n 1)"
echo "python:            $(python3 --version 2>&1)"
fails=0; passes=0; nest=0; boot_ne=0; ek_local=0; rootok=0
ok()  { echo "PASS             $1"; passes=$((passes+1)); }
bad() { echo "FAIL             $1"; fails=$((fails+1)); }
ne()  { echo "NOT ESTABLISHED  $1"; nest=$((nest+1)); }
why() { printf '%s\n' "$1" | grep -i -m 1 'error\|not found\|cannot' || printf '%s\n' "$1" | tail -n 1; }
tlabel() { case "$1" in *"has expired"*) echo "certificate expired";; *"not yet valid"*) echo "certificate not yet valid";; *) echo "certificate outside its validity dates";; esac; }
TIMENOTE="the signature and chain verify to the release root when validity dates are ignored; nothing in these files shows the signature was made while the certificate was valid"
chk() { if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 (got: $2)"; fi; }
listed() { awk -v f="$2" '$2==f {print $1}' "$1" | head -n 1; }
# a certificate given as DER or PEM, written as DER to $2
toder() { openssl x509 -inform DER -in "$1" -outform DER -out "$2" 2>/dev/null || openssl x509 -inform PEM -in "$1" -outform DER -out "$2" 2>/dev/null; }

echo "== files"
FILES="$ROOTF $RIM $RIM.p7s SHA256SUMS $ARCH.tar.gz"
if [ -n "$SRC" ]; then
  got=1; for f in $FILES; do cp "$SRC/$f" . || got=0; done
  [ "$got" -eq 1 ] && ok "files copied from $SRC" || { bad "files copy from $SRC"; exit 1; }
else
  got=1; for f in $FILES; do curl -sSfL -m 120 -o "$f" "$REL/$f" || got=0; done
  [ "$got" -eq 1 ] && ok "files downloaded from the $TAG release" || { bad "download from $REL"; exit 1; }
fi
for f in "$ARCH.tar.gz" "$RIM" "$RIM.p7s"; do
  l=$(listed SHA256SUMS "$f")
  if [ -z "$l" ]; then bad "$f is not listed in the release SHA256SUMS"
  else chk "$f matches the release SHA256SUMS" "$(sha256sum "$f" | cut -d' ' -f1)" "$l"; fi
done
l=$(listed SHA256SUMS "verify-l3.sh")
if [ -z "$l" ]; then ne "this script: verify-l3.sh is not listed in the release SHA256SUMS, so the release signature does not cover it; compare its sha256 above with a copy you obtained through your own channel"
elif [ "$SELF" = "$l" ]; then ok "this script is the one listed in the release SHA256SUMS"
else bad "this script differs from the verify-l3.sh listed in the release SHA256SUMS"; fi
ne "Sigstore signature over the release SHA256SUMS: not checked by this script; scripts/verify-release.sh --repo $REPO --board $BOARD --tag $TAG checks it, and every line above rests on it"
echo "== archive contents"
tl=$(tar -tvzf "$ARCH.tar.gz" 2>&1) || { bad "cannot list the evidence archive"; exit 1; }
if printf '%s\n' "$tl" | awk -v d="$ARCH/" '{t=substr($1,1,1); n=$NF; r=substr(n,length(d)+1)} !((t=="-" && index(n,d)==1 && r!="" && index(r,"/")==0) || (t=="d" && n==d)) {x=1} END{exit x}'; then ok "archive entries: regular files directly under $ARCH/"
else bad "archive entries: something other than a regular file directly under $ARCH/ (a link, a device, a nested or outside path); the archive is not unpacked"; exit 1; fi
want=$(tar -xzOf "$ARCH.tar.gz" "$ARCH/SHA256SUMS" 2>/dev/null | awk '{print $2}')
dup=$(printf '%s\n' "$want" | sort | uniq -d)
if [ -z "$want" ]; then bad "archive SHA256SUMS: missing or empty"
elif [ -n "$dup" ]; then bad "archive SHA256SUMS names a file more than once: $(echo $dup)"
else ok "archive SHA256SUMS names each file once"; fi
exp=$(printf '%s\n' $want SHA256SUMS SHA256SUMS.p7s | sed "s|^|$ARCH/|" | sort)
got=$(tar -tzf "$ARCH.tar.gz" | grep -Fvx "$ARCH/" | sort)
if [ "$got" = "$exp" ]; then ok "archive holds exactly the files its SHA256SUMS names, plus SHA256SUMS and SHA256SUMS.p7s"
else bad "archive contents differ from its SHA256SUMS (< named but absent, > present but not named): $(diff <(printf '%s\n' "$exp") <(printf '%s\n' "$got") | grep '^[<>]' | tr '\n' ' ')"; fi
tar -xzf "$ARCH.tar.gz" || { bad "cannot unpack the evidence archive"; exit 1; }
mv "$ROOTF" "$RIM" "$RIM.p7s" "$ARCH/"
cd "$ARCH" || exit 1
if sha256sum -c --quiet SHA256SUMS; then ok "archive SHA256SUMS"; else bad "archive SHA256SUMS"; fi

echo "== step 1: release root"
fp=$(openssl x509 -in "$ROOTF" -noout -fingerprint -sha256 | cut -d= -f2)
chk "root fingerprint" "$fp" "$ROOT_FP"
[ "$fp" = "$ROOT_FP" ] && rootok=1

echo "== step 1a: evidence list signature"
rm -f ev-out.pem
out=$(openssl cms -verify -binary -inform DER -in SHA256SUMS.p7s -content SHA256SUMS -CAfile "$ROOTF" -certfile signing-ca.pem -purpose any -signer ev-out.pem -out /dev/null 2>&1)
if [ "$out" = "CMS Verification successful" ]; then ok "archive SHA256SUMS signature"
else
  out2=$(openssl cms -verify -no_check_time -binary -inform DER -in SHA256SUMS.p7s -content SHA256SUMS -CAfile "$ROOTF" -certfile signing-ca.pem -purpose any -signer ev-out.pem -out /dev/null 2>&1)
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
out=$(openssl verify -CAfile "$ROOTF" -untrusted signing-ca.pem reg-signer.pem 2>&1)
if [ "$out" = "reg-signer.pem: OK" ]; then ok "leaf chain"
else
  out2=$(openssl verify -no_check_time -CAfile "$ROOTF" -untrusted signing-ca.pem reg-signer.pem 2>&1)
  if [ "$rootok" -eq 1 ] && [ "$out2" = "reg-signer.pem: OK" ]; then bad "leaf chain: $(tlabel "$out"); the chain verifies to the release root when validity dates are ignored"
  else r="$out2"; [ "$out2" = "reg-signer.pem: OK" ] && r="$out"; bad "leaf chain: does not chain to the release root (got: $(why "$r"))"; fi
fi
eku=$(openssl x509 -in reg-signer.pem -noout -ext extendedKeyUsage | tr -d ' \n')
chk "leaf EKU" "$eku" "$REG_EKU"

echo "== step 3: record signature"
out=$(openssl cms -verify -binary -inform DER -in "$REG.p7s" -content "$REG" -CAfile "$ROOTF" -certfile signing-ca.pem -purpose any -signer signer-out.pem -out /dev/null 2>&1)
if [ "$out" = "CMS Verification successful" ]; then ok "record CMS"
else
  out2=$(openssl cms -verify -no_check_time -binary -inform DER -in "$REG.p7s" -content "$REG" -CAfile "$ROOTF" -certfile signing-ca.pem -purpose any -signer signer-out.pem -out /dev/null 2>&1)
  if [ "$rootok" -eq 1 ] && [ "$out2" = "CMS Verification successful" ]; then bad "record CMS: $(tlabel "$out"); $TIMENOTE"
  else rm -f signer-out.pem; r="$out2"; [ "$out2" = "CMS Verification successful" ] && r="$out"; bad "record CMS: signature does not verify or does not chain to the release root (got: $(why "$r"))"; fi
fi
if [ -s signer-out.pem ]; then
  a=$(openssl x509 -in signer-out.pem -noout -fingerprint -sha256)
  b=$(openssl x509 -in reg-signer.pem -noout -fingerprint -sha256)
  chk "record signer is the leaf" "$a" "$b"
else bad "record signer is the leaf: could not run, no signer was extracted because the record signature did not verify"; fi
ne "registration event: the record is the signed statement of whoever holds the release root that this AK was registered against this EK; that the registration happened as the record states is not established by these files"

echo "== step 4: EK chain and record contents"
if [ "$INFINEON" -eq 1 ]; then
  if curl -sSf -m 30 -o mfr034.crt https://pki.infineon.com/OptigaRsaMfrCA034/OptigaRsaMfrCA034.crt \
     && curl -sSf -m 30 -o root.crt https://pki.infineon.com/OptigaRsaRootCA/OptigaRsaRootCA.crt \
     && openssl x509 -inform DER -in mfr034.crt -noout 2>/dev/null \
     && openssl x509 -inform DER -in root.crt -noout 2>/dev/null; then
    ok "Infineon CAs downloaded from Infineon"
  else
    echo "INFO             Infineon not reachable or did not return certificates, using the copies in the archive"
    cp infineon-mfr034.crt mfr034.crt; cp infineon-root.crt root.crt
    ek_local=1
  fi
else
  if toder "$EKINT" mfr034.crt && toder "$EKROOT" root.crt; then ok "EK CAs read from the files given"
  else bad "EK CAs: --ek-root or --ek-intermediate is not a certificate in DER or PEM"; fi
fi
openssl x509 -inform DER -in root.crt -out root.pem
openssl x509 -inform DER -in mfr034.crt -out mfr034.pem
openssl x509 -inform DER -in ek.der -out ek.pem
out=$(openssl verify -CAfile root.pem -untrusted mfr034.pem ek.pem 2>&1)
chk "EK chain" "$out" "ek.pem: OK"
fp=$(openssl x509 -in root.pem -noout -fingerprint -sha256 | cut -d= -f2)
if [ -n "$EKROOT_FP" ]; then
  if [ "$INFINEON" -eq 1 ]; then chk "Infineon root fingerprint" "$fp" "$EKROOT_FP"
  else chk "EK root fingerprint" "$fp" "$EKROOT_FP"; fi
else
  ne "EK root fingerprint: no --ek-root-fp was given, so only the file passed as --ek-root pins the root; confirm $fp through a channel of your own"
fi
if [ "$ek_local" -eq 1 ]; then
  ne "EK chain independent of the release signer: the Infineon certificates came from the archive and the root fingerprint is compared with a value in this script; confirm $fp through a channel of your own"
fi
rs=$(python3 -c "import json; print(json.load(open('$REG'))['root_sha256'])")
im=$(python3 -c "import json,hashlib; print(hashlib.sha256(bytes.fromhex(json.load(open('$REG'))['intermediate_certificate'])).hexdigest())")
chk "issuing CA equals record" "$im" "$(sha256sum mfr034.crt | cut -d' ' -f1)"
chk "record root_sha256" "$rs" "$(echo "$fp" | tr -d ':' | tr 'A-F' 'a-f')"
rec=$(python3 -c "import json,hashlib; d=json.load(open('$REG')); print(hashlib.sha256(bytes.fromhex(d['ek_certificate'])).hexdigest(), hashlib.sha256(bytes.fromhex(d['ak_public'])).hexdigest())")
fil="$(sha256sum ek.der | cut -d' ' -f1) $(sha256sum ak.pub | cut -d' ' -f1)"
chk "ek.der and ak.pub are the signed ones" "$rec" "$fil"
# Record format 2 carries the CRLs the registrar checked (tactiq-attest
# DDR-005 boundary D, amended): the EK against the issuing CA's CRL, the
# issuing CA against the root's CRL, at chain_checked_unix. They are
# re-checked here from the signed record, not taken on the record's word.
rf=$(python3 -c "import json; print(json.load(open('$REG')).get('format'))")
rv=$(python3 -c "import json; print(json.load(open('$REG')).get('revocation_checked'))")
if [ "$rf" = "tactiq-ak-registration/2" ] && [ "$rv" = "True" ]; then
  python3 -c "import json; d=json.load(open('$REG')); open('ek-crl.der','wb').write(bytes.fromhex(d['ek_crl'])); open('int-crl.der','wb').write(bytes.fromhex(d['intermediate_crl']))"
  chk "EK CRL signed by the issuing CA" "$(openssl crl -inform DER -in ek-crl.der -CAfile mfr034.pem -noout 2>&1)" "verify OK"
  chk "issuing CA CRL signed by the root" "$(openssl crl -inform DER -in int-crl.der -CAfile root.pem -noout 2>&1)" "verify OK"
  cc=$(python3 -c "import json; print(json.load(open('$REG'))['chain_checked_unix'])")
  for pair in "ek-crl.der:ek.pem:EK certificate" "int-crl.der:mfr034.pem:issuing CA"; do
    c="${pair%%:*}"; rest="${pair#*:}"; cert="${rest%%:*}"; what="${rest#*:}"
    ser=$(openssl x509 -in "$cert" -noout -serial | cut -d= -f2)
    if openssl crl -inform DER -in "$c" -noout -text | grep -qi "Serial Number: *${ser}\$"; then bad "$what: REVOKED in its CRL (serial $ser)"
    else ok "$what not listed in its CRL"; fi
    lu=$(date -u -d "$(openssl crl -inform DER -in "$c" -noout -lastupdate | cut -d= -f2)" +%s)
    nu=$(date -u -d "$(openssl crl -inform DER -in "$c" -noout -nextupdate | cut -d= -f2)" +%s)
    if [ "$lu" -le "$cc" ] && [ "$cc" -le "$nu" ]; then ok "$what CRL current at the chain check time"
    else bad "$what CRL not current at the chain check time ($lu..$nu, checked $cc)"; fi
  done
  ne "revocation after the registration: the CRLs are those current at the chain check time; a later revocation is not covered by these files"
else ne "EK certificate not revoked: record format $rf says revocation_checked=$rv"; fi

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
if [ "$BOARD" = rock5a ]; then
  ne "origin of the TPM reset before this boot: resetCount is signed, but SPL drives the TPM reset line and the running system can drive it too, so a reset is not by itself evidence of a reboot (revenue7-eng/tactiq-os#224)"
else
  ne "origin of the TPM reset before this boot: resetCount is signed, but whether a TPM reset implies a reboot depends on how board $BOARD drives the TPM reset line; this evidence does not show it"
fi
ne "freshness: qualifying data is the hash of the agent's own record, not a challenge chosen by the reviewer"

echo "== step 6a: TPM firmware"
if [ -z "$TPM_FW_MIN" ]; then
  ne "TPM firmware: no --tpm-fw-min was given for this EK root, so no minimum firmware version is checked"
else
  for q in $QUOTES; do
    fw=$(python3 - "$q.attest" <<'PY'
import struct, sys
b = open(sys.argv[1], 'rb').read()
o = 6
o += 2 + struct.unpack('>H', b[o:o+2])[0]          # qualifiedSigner
o += 2 + struct.unpack('>H', b[o:o+2])[0]          # extraData
o += 17                                            # clockInfo
v = struct.unpack('>Q', b[o:o+8])[0]
hi, lo = v >> 32, v & 0xffffffff
print(f"{v:#018x} {hi >> 16}.{hi & 0xffff}.{lo >> 8}.{lo & 0xff}")
PY
)
    fwv=${fw%% *}; fwd=${fw#* }
    if [ "$INFINEON" -eq 1 ]; then shown="$fwd"; floor="7.87"; else shown="$fwv"; floor="$TPM_FW_MIN"; fi
    if [ -z "$fw" ]; then bad "TPM firmware in quote $q: firmwareVersion could not be read"
    elif [ $((fwv)) -ge $((TPM_FW_MIN)) ] 2>/dev/null; then ok "TPM firmware in quote $q: $shown (minimum $floor)"
    elif [ "$INFINEON" -eq 1 ]; then bad "TPM firmware in quote $q: $fwd is below the minimum 7.87; Infineon lists SLB 9670 firmware below 7.87 as affected by CVE-2025-2884 and CVE-2026-6726"
    else bad "TPM firmware in quote $q: $fwv is below the minimum $TPM_FW_MIN given by --tpm-fw-min"; fi
  done
fi

echo "== step 7: boot state against the RIM"
out=$(openssl cms -verify -binary -inform DER -in "$RIM.p7s" -content "$RIM" -CAfile "$ROOTF" -purpose any -signer rim-signer.pem -out /dev/null 2>&1)
rimok=0
if [ "$out" = "CMS Verification successful" ]; then ok "RIM CMS"; rimok=1
else
  out2=$(openssl cms -verify -no_check_time -binary -inform DER -in "$RIM.p7s" -content "$RIM" -CAfile "$ROOTF" -purpose any -signer rim-signer.pem -out /dev/null 2>&1)
  if [ "$rootok" -eq 1 ] && [ "$out2" = "CMS Verification successful" ]; then bad "RIM CMS: $(tlabel "$out"); $TIMENOTE"
  else rm -f rim-signer.pem; r="$out2"; [ "$out2" = "CMS Verification successful" ] && r="$out"; bad "RIM CMS: signature does not verify or does not chain to the release root (got: $(why "$r"))"; fi
fi
if [ -s rim-signer.pem ]; then
  eku=$(openssl x509 -in rim-signer.pem -noout -ext extendedKeyUsage 2>/dev/null | tr -d ' \n')
  [ "$eku" = "$RIM_EKU" ] || rimok=0
  chk "RIM signer EKU" "$eku" "$RIM_EKU"
else bad "RIM signer EKU: could not run, no signer was extracted because the RIM signature did not verify"; fi
# every composite the RIM allows: per slot, and per listed value of a PCR
refs=$(python3 - "$RIM" <<'PY'
import json, hashlib, itertools, sys
p = json.load(open(sys.argv[1]))['pcr']
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
if [ -z "$refs" ]; then bad "RIM reference: no composite could be computed from $RIM"; rimok=0
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
s8=$(python3 - "$PWD" "$FIRSTQ" "$RIM" <<'PY'
import hashlib, json, struct, sys, os
d, q, rimf = sys.argv[1], sys.argv[2], sys.argv[3]
h = lambda b: hashlib.sha256(b).digest()
z = bytes(32)
sep = {h(z + h(b'\x00' * 4)).hex(): "separator 0x00000000",
       h(z + h(b'\xff' * 4)).hex(): "separator 0xFFFFFFFF"}
rim = json.load(open(os.path.join(d, rimf)))['pcr']['values']
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
ne "files on the root filesystem: the PCR values cover the boot chain up to the kernel, its device tree and its command line; whether the root filesystem is verity-protected and whether IMA runs in the image are stated in the release's coverage manifest, if it has one; this script does not check either"

echo
echo "PASS: $passes   FAIL: $fails   NOT ESTABLISHED: $nest"
# exit 0: nothing failed and the boot state matched the reference
# exit 1: at least one check failed
# exit 2: nothing failed, but the boot state was not established
if [ "$fails" -ne 0 ]; then echo "FAILED CHECKS: $fails"; exit 1
elif [ "$boot_ne" -ne 0 ]; then echo "BOOT STATE NOT ESTABLISHED. This is not a pass."; exit 2
else echo "NO CHECK FAILED. Read the NOT ESTABLISHED lines: they are not passes."; exit 0; fi
