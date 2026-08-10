#!/usr/bin/env bash
#
# gen-pki.sh — generate signing hierarchies for TactiQ OS RAUC bundles.
#
#   ./gen-pki.sh dev    -> pki/dev/    unencrypted keys, CI-usable
#   ./gen-pki.sh prod   -> pki/prod/   encrypted keys, OFFLINE MACHINE ONLY
#   ./gen-pki.sh ima    -> pki/dev/    IMA appraisal leaf, existing hierarchy
#
# Hierarchy (both flavours):
#   Root CA  ->  Signing CA  ->  Signer (leaf)
#
# Only the Root CA certificate goes into the device keyring.
# The Signing CA certificate travels inside the bundle signature.
#
set -euo pipefail

FLAVOUR="${1:-}"
case "$FLAVOUR" in
  dev)
    OUT="pki/dev"
    ORG="TactiQ"
    ROOT_CN="TactiQ OS DEVELOPMENT CA - NOT FOR PRODUCTION"
    ICA_CN="TactiQ OS DEVELOPMENT Signing CA - NOT FOR PRODUCTION"
    LEAF_CN="TactiQ OS DEVELOPMENT Signer (CI) - NOT FOR PRODUCTION"
    ENC=""                 # no passphrase: this key lives in CI
    ROOT_DAYS=730
    ICA_DAYS=730
    LEAF_DAYS=90
    ;;
  prod)
    OUT="pki/prod"
    ORG="TactiQ"
    ROOT_CN="TactiQ Release Root CA"
    ICA_CN="TactiQ Release Signing CA"
    LEAF_CN="TactiQ Release Signer - Andrey"
    ENC="-aes-256-cbc"     # passphrase required
    ROOT_DAYS=3650
    ICA_DAYS=1095
    LEAF_DAYS=730          # deliberately long: device clock may drift (see O-3)
    ;;
  ima)
    OUT="pki/dev"
    ORG="TactiQ"
    LEAF_CN="TactiQ OS DEVELOPMENT IMA Signer - NOT FOR PRODUCTION"
    ENC=""
    LEAF_DAYS=730
    ;;
  *)
    echo "usage: $0 {dev|prod|ima}" >&2
    exit 1
    ;;
esac

if [ "$FLAVOUR" = "ima" ]; then
  for f in signing-ca.key.pem signing-ca.pem root-ca.pem; do
    if [ ! -e "$OUT/$f" ]; then
      echo "ERROR: $OUT/$f not found. Run '$0 dev' first." >&2
      exit 1
    fi
  done
  for f in ima-signer.key.pem ima-signer.pem ima-signer.der; do
    if [ -e "$OUT/$f" ]; then
      echo "ERROR: $OUT/$f already exists. Refusing to reissue in place:" >&2
      echo "       a new key invalidates every signature in a built rootfs." >&2
      exit 1
    fi
  done
  cd "$OUT"
elif [ -e "$OUT" ]; then
  echo "ERROR: $OUT already exists. Refusing to overwrite an existing hierarchy." >&2
  exit 1
fi

if [ "$FLAVOUR" = "ima" ]; then
  # ------------------------------------------------------------ IMA leaf
  # Issued from the existing dev Signing CA. No codeSigning EKU: the key
  # signs file hashes through evmctl, not code objects, and RAUC must not
  # accept it as a bundle signer.
  cat > ima-signer.cnf <<'EOF'
[v3_signer]
basicConstraints       = critical, CA:FALSE
keyUsage               = critical, digitalSignature
subjectKeyIdentifier   = hash
authorityKeyIdentifier = keyid:always
EOF

  echo "[1/1] IMA appraisal signer (leaf)"
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 \
    $ENC -out ima-signer.key.pem
  openssl req -new -sha256 \
    -key ima-signer.key.pem \
    -subj "/O=$ORG/CN=$LEAF_CN" \
    -out ima-signer.csr
  openssl x509 -req -sha256 \
    -in ima-signer.csr \
    -CA signing-ca.pem -CAkey signing-ca.key.pem -CAcreateserial \
    -days "$LEAF_DAYS" \
    -extfile ima-signer.cnf -extensions v3_signer \
    -out ima-signer.pem
  rm -f ima-signer.csr

  # IMA_EVM_X509 is handed to evmctl, which expects DER.
  openssl x509 -in ima-signer.pem -outform der -out ima-signer.der

  # IMA_EVM_ROOT_CA is compiled into the kernel's builtin keyring. The leaf
  # is included alongside the two CAs: with
  # CONFIG_IMA_KEYRINGS_PERMIT_SIGNED_BY_BUILTIN_OR_SECONDARY the kernel
  # verifies file signatures against keys it holds, so the signing
  # certificate itself has to be one of them.
  cat root-ca.pem signing-ca.pem ima-signer.pem > system-trusted-bundle.pem

  echo
  echo "---- verification ----------------------------------------------"
  openssl verify -CAfile root-ca.pem -untrusted signing-ca.pem ima-signer.pem
  echo
  echo "leaf key usage:"
  openssl x509 -in ima-signer.pem -noout -text \
    | grep -A1 -E 'X509v3 (Key Usage|Extended Key Usage)'
  echo
  openssl x509 -in ima-signer.pem -noout -subject -enddate

  cat <<EOF

---- files ------------------------------------------------------
$OUT/ima-signer.pem              PUBLIC  -> certificate
$OUT/ima-signer.der              PUBLIC  -> IMA_EVM_X509, passed to evmctl
$OUT/system-trusted-bundle.pem   PUBLIC  -> IMA_EVM_ROOT_CA, into the kernel
$OUT/ima-signer.key.pem          PRIVATE -> IMA_EVM_PRIVKEY

---- next -------------------------------------------------------
The variables above are set in conf/distro/tactiq.conf. Rebuilding
tactiq-image-dev signs the rootfs with this key; every previously
built image carries signatures from the old one.
EOF
  exit 0
fi

mkdir -p "$OUT"
cd "$OUT"

if [ "$FLAVOUR" = "prod" ]; then
  echo
  echo "=============================================================="
  echo " PRODUCTION HIERARCHY"
  echo " Run this on an OFFLINE machine only."
  echo " Private keys generated here must never touch a networked host."
  echo "=============================================================="
  echo
fi

# ---------------------------------------------------------------- extensions

cat > root-ca.cnf <<'EOF'
[v3_root]
basicConstraints     = critical, CA:TRUE, pathlen:1
keyUsage             = critical, keyCertSign, cRLSign
subjectKeyIdentifier = hash
EOF

cat > signing-ca.cnf <<'EOF'
[v3_intermediate]
basicConstraints       = critical, CA:TRUE, pathlen:0
keyUsage               = critical, keyCertSign, cRLSign
subjectKeyIdentifier   = hash
authorityKeyIdentifier = keyid:always
EOF

# codeSigning EKU is mandatory: RAUC with check-purpose=codesign rejects the
# chain without it, and bundle creation fails with "unsupported certificate
# purpose" even locally.
cat > signer.cnf <<'EOF'
[v3_signer]
basicConstraints       = critical, CA:FALSE
keyUsage               = critical, digitalSignature
extendedKeyUsage       = critical, codeSigning
subjectKeyIdentifier   = hash
authorityKeyIdentifier = keyid:always
EOF

# ---------------------------------------------------------------- root CA

echo "[1/3] Root CA"
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:4096 \
  $ENC -out root-ca.key.pem

openssl req -x509 -new -sha256 \
  -key root-ca.key.pem \
  -days "$ROOT_DAYS" \
  -subj "/O=$ORG/CN=$ROOT_CN" \
  -config root-ca.cnf -extensions v3_root \
  -out root-ca.pem

# ---------------------------------------------------------------- signing CA

echo "[2/3] Signing CA"
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:4096 \
  $ENC -out signing-ca.key.pem

openssl req -new -sha256 \
  -key signing-ca.key.pem \
  -subj "/O=$ORG/CN=$ICA_CN" \
  -out signing-ca.csr

openssl x509 -req -sha256 \
  -in signing-ca.csr \
  -CA root-ca.pem -CAkey root-ca.key.pem -CAcreateserial \
  -days "$ICA_DAYS" \
  -extfile signing-ca.cnf -extensions v3_intermediate \
  -out signing-ca.pem

# ---------------------------------------------------------------- leaf

echo "[3/3] Signer (leaf)"
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 \
  $ENC -out signer.key.pem

openssl req -new -sha256 \
  -key signer.key.pem \
  -subj "/O=$ORG/CN=$LEAF_CN" \
  -out signer.csr

openssl x509 -req -sha256 \
  -in signer.csr \
  -CA signing-ca.pem -CAkey signing-ca.key.pem -CAcreateserial \
  -days "$LEAF_DAYS" \
  -extfile signer.cnf -extensions v3_signer \
  -out signer.pem

rm -f signing-ca.csr signer.csr

# ---------------------------------------------------------------- verify

echo
echo "---- verification ----------------------------------------------"

openssl verify -CAfile root-ca.pem -untrusted signing-ca.pem signer.pem

echo
echo "leaf key usage:"
openssl x509 -in signer.pem -noout -text \
  | grep -A1 -E 'X509v3 (Key Usage|Extended Key Usage)'

echo
echo "chain:"
openssl x509 -in root-ca.pem    -noout -subject -enddate
openssl x509 -in signing-ca.pem -noout -subject -enddate
openssl x509 -in signer.pem     -noout -subject -enddate

# ---------------------------------------------------------------- summary

cat <<EOF

---- files ------------------------------------------------------
$OUT/root-ca.pem        PUBLIC  -> device keyring (/etc/rauc/)
$OUT/signing-ca.pem     PUBLIC  -> embedded in bundle signature
$OUT/signer.pem         PUBLIC  -> embedded in bundle signature
$OUT/*.key.pem          PRIVATE
EOF

if [ "$FLAVOUR" = "prod" ]; then
cat <<'EOF'

---- next -------------------------------------------------------
Copy ONLY the three .pem certificates off this machine.
The *.key.pem files must stay on the offline host / encrypted media.
Never commit pki/prod/*.key.pem. Never place them in CI secrets.
EOF
else
cat <<'EOF'

---- next -------------------------------------------------------
signer.key.pem is committed, not secret: dev signing is reproducible
from outside by design (see pki/README.md).
root-ca.pem is the DEV keyring and is installed only when
TACTIQ_KEYRING = "dev". Any other value makes recipes-core/rauc refuse to
parse until RAUC_KEYRING_FILE_EXTERNAL supplies a keyring from outside the
tree, so this root cannot reach a production image by omission.
EOF
fi

echo
