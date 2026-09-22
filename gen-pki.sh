#!/usr/bin/env bash
#
# gen-pki.sh — generate signing hierarchies for TactiQ OS RAUC bundles.
#
#   ./gen-pki.sh dev    -> pki/dev/    unencrypted keys, CI-usable
#   ./gen-pki.sh ima    -> pki/dev/    IMA appraisal leaf, existing hierarchy
#   ./gen-pki.sh fit    -> pki/dev/    U-Boot FIT signer, self-signed
#   ./gen-pki.sh rim    -> pki/dev/    RIM signer leaf, existing hierarchy
#
#   ./gen-pki.sh prod DIR          release RAUC hierarchy, encrypted keys
#   ./gen-pki.sh ima-prod DIR      release IMA leaf from the release Signing CA
#   ./gen-pki.sh fit-prod DIR      release U-Boot FIT signer, self-signed
#   ./gen-pki.sh modsign-prod DIR  release kernel module signing key
#   ./gen-pki.sh rim-prod CA_DIR DIR
#                                  release RIM signer leaf from the release
#                                  Signing CA in CA_DIR, written to DIR
#
# DIR is required for every release flavour and must lie outside this
# repository: release keys live on encrypted removable media, attached only
# while the machine is offline (pki/README.md). ima-prod, fit-prod and
# modsign-prod write their keys without a passphrase, because mkimage,
# evmctl and the kernel build read them unattended inside bitbake; their
# protection is the encrypted medium. Only prod (the RAUC hierarchy, used
# offline by rauc resign) keeps passphrase-encrypted keys, and rim-prod,
# whose key signs the RIM in mk-release.sh outside bitbake.
#
# Hierarchy (both flavours):
#   Root CA  ->  Signing CA  ->  Signer (leaf)
#
# Only the Root CA certificate goes into the device keyring.
# The Signing CA certificate travels inside the bundle signature.
#
set -euo pipefail

# Private keys are created by this script and never re-chmod'ed afterwards,
# so the mode they are born with is the mode they keep. 077 makes that mode
# 0600 for every flavour, including prod on the offline host.
umask 077

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
    OUT="${2:-}"
    ORG="TactiQ"
    ROOT_CN="TactiQ Release Root CA"
    ICA_CN="TactiQ Release Signing CA"
    LEAF_CN="TactiQ Release Signer - Andrey"
    ENC="-aes-256-cbc"     # passphrase required
    ROOT_DAYS=3650
    ICA_DAYS=1095
    LEAF_DAYS=730          # deliberately long: device clock may drift (see O-3)
    ;;
  fit)
    OUT="pki/dev"
    ORG="TactiQ"
    LEAF_CN="TactiQ OS DEVELOPMENT FIT Signer - NOT FOR PRODUCTION"
    ENC=""
    LEAF_DAYS=730
    ;;
  ima)
    OUT="pki/dev"
    ORG="TactiQ"
    LEAF_CN="TactiQ OS DEVELOPMENT IMA Signer - NOT FOR PRODUCTION"
    ENC=""
    LEAF_DAYS=730
    ;;
  signer)
    OUT="pki/dev"
    ORG="TactiQ"
    LEAF_CN="TactiQ OS DEVELOPMENT Signer (CI) - NOT FOR PRODUCTION"
    ENC=""                 # as dev: this key lives in CI
    LEAF_DAYS=90           # as dev
    ;;
  fit-prod)
    OUT="${2:-}"
    ORG="TactiQ"
    LEAF_CN="TactiQ OS Release FIT Signer"
    ENC=""
    LEAF_DAYS=3650         # U-Boot checks only the modulus, not the dates
    ;;
  ima-prod)
    OUT="${2:-}"
    ORG="TactiQ"
    LEAF_CN="TactiQ OS Release IMA Signer"
    ENC=""
    LEAF_DAYS=730
    ;;
  modsign-prod)
    OUT="${2:-}"
    ORG="TactiQ OS"
    LEAF_CN="TactiQ OS release module signing key"
    ENC=""
    LEAF_DAYS=36500        # as the dev key and the kernel default genkey
    ;;
  rim)
    CA_DIR="pki/dev"
    OUT="pki/dev"
    ORG="TactiQ"
    LEAF_CN="TactiQ OS DEVELOPMENT RIM Signer - NOT FOR PRODUCTION"
    ENC=""
    LEAF_DAYS=730
    ;;
  rim-prod)
    CA_DIR="${2:-}"
    OUT="${3:-}"
    ORG="TactiQ"
    LEAF_CN="TactiQ OS Release RIM Signer"
    ENC="-aes-256-cbc"     # passphrase required: read by mk-release.sh, not bitbake
    # A verifier validates the whole path at verification time, so a RIM
    # stops verifying when the Signing CA expires, whatever this value is.
    # Matching the Signing CA lifetime states that bound instead of hiding it.
    LEAF_DAYS=1095
    ;;
  *)
    echo "usage: $0 {dev|ima|fit|signer}" >&2
    echo "       $0 {prod|ima-prod|fit-prod|modsign-prod} DIR" >&2
    echo "       $0 rim" >&2
    echo "       $0 rim-prod CA_DIR DIR" >&2
    exit 1
    ;;
esac

# Release flavours: DIR is mandatory and must be outside the repository.
case "$FLAVOUR" in
  prod|ima-prod|fit-prod|modsign-prod)
    if [ -z "$OUT" ]; then
      echo "ERROR: $FLAVOUR needs an output directory: $0 $FLAVOUR DIR" >&2
      exit 1
    fi
    REPO="$(cd "$(dirname "$0")" && pwd -P)"
    ABS="$(realpath -m "$OUT")"
    case "$ABS/" in
      "$REPO"/*)
        echo "ERROR: $OUT is inside the repository ($REPO)." >&2
        echo "       Release keys must live outside it, on encrypted media." >&2
        exit 1
        ;;
    esac
    OUT="$ABS"
    ;;
  rim-prod)
    if [ -z "$CA_DIR" ] || [ -z "$OUT" ]; then
      echo "ERROR: rim-prod needs the Signing CA directory and an output directory:" >&2
      echo "       $0 rim-prod CA_DIR DIR" >&2
      exit 1
    fi
    REPO="$(cd "$(dirname "$0")" && pwd -P)"
    for d in "$CA_DIR" "$OUT"; do
      case "$(realpath -m "$d")/" in
        "$REPO"/*)
          echo "ERROR: $d is inside the repository ($REPO)." >&2
          echo "       Release keys must live outside it, on encrypted media." >&2
          exit 1
          ;;
      esac
    done
    CA_DIR="$(realpath -m "$CA_DIR")"
    OUT="$(realpath -m "$OUT")"
    ;;
esac

if [ "$FLAVOUR" = "rim" ] || [ "$FLAVOUR" = "rim-prod" ]; then
  # ------------------------------------------------------------ RIM signer
  # Signs the Reference Integrity Manifest (RELEASE_INTEGRITY.md §5): the
  # file that binds the published PCR reference to the release Root CA.
  # Issued from the Signing CA, so an operator verifies a RIM against the
  # same Root CA as a bundle and needs nothing else.
  #
  # Its only extended key usage is the private OID below, marked critical.
  # No codeSigning: RAUC (check-purpose=codesign-rauc in system.conf) must
  # refuse this key as a bundle signer, and no other consumer that checks
  # purposes should accept it for anything but a RIM. The OID is a UUID
  # arc (ITU-T X.667, 2.25.<uuid as integer>), which needs no registration;
  # it is fixed here once and a verifier checks for exactly this value.
  #
  # RSA-3072 like the other leaves: the chain above it is RSA, so anything
  # that validates the chain, a browser included, already verifies RSA.
  #
  # In rim-prod the Signing CA stays in CA_DIR and only the leaf is written
  # to DIR: the CA keys and the build keys live in separate containers.
  # CA_DIR must be writable, because -CAcreateserial updates the serial
  # file next to the Signing CA certificate.
  RIM_EKU_OID="2.25.209288284150790823604684143005475146259"
  CA_DIR="$(realpath -m "$CA_DIR")"

  for f in signing-ca.key.pem signing-ca.pem root-ca.pem; do
    if [ ! -e "$CA_DIR/$f" ]; then
      echo "ERROR: $CA_DIR/$f not found. Create the hierarchy first ($0 dev, or $0 prod DIR)." >&2
      exit 1
    fi
  done
  mkdir -p "$OUT"
  for f in rim-signer.key.pem rim-signer.pem; do
    if [ -e "$OUT/$f" ]; then
      echo "ERROR: $OUT/$f already exists. Refusing to reissue in place:" >&2
      echo "       published RIMs name the certificate that signed them." >&2
      exit 1
    fi
  done
  cd "$OUT"

  cat > rim-signer.cnf <<EOF
[v3_signer]
basicConstraints       = critical, CA:FALSE
keyUsage               = critical, digitalSignature
extendedKeyUsage       = critical, $RIM_EKU_OID
subjectKeyIdentifier   = hash
authorityKeyIdentifier = keyid:always
EOF

  echo "[1/1] RIM signer (leaf)"
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 \
    $ENC -out rim-signer.key.pem
  openssl req -new -sha256 \
    -key rim-signer.key.pem \
    -subj "/O=$ORG/CN=$LEAF_CN" \
    -out rim-signer.csr
  openssl x509 -req -sha256 \
    -in rim-signer.csr \
    -CA "$CA_DIR/signing-ca.pem" -CAkey "$CA_DIR/signing-ca.key.pem" \
    -CAcreateserial \
    -days "$LEAF_DAYS" \
    -extfile rim-signer.cnf -extensions v3_signer \
    -out rim-signer.pem
  rm -f rim-signer.csr

  echo
  echo "---- verification ----------------------------------------------"
  openssl verify -CAfile "$CA_DIR/root-ca.pem" \
    -untrusted "$CA_DIR/signing-ca.pem" rim-signer.pem
  echo
  echo "leaf key usage:"
  openssl x509 -in rim-signer.pem -noout -text \
    | grep -A1 -E 'X509v3 (Key Usage|Extended Key Usage)'
  if openssl x509 -in rim-signer.pem -noout -text | grep -q 'Code Signing'; then
    echo "ERROR: rim-signer.pem carries codeSigning; RAUC would accept it." >&2
    exit 1
  fi
  echo
  openssl x509 -in rim-signer.pem -noout -subject -issuer -enddate

  cat <<EOF

---- files ------------------------------------------------------
$OUT/rim-signer.pem       PUBLIC  -> RIM signer certificate
$OUT/rim-signer.key.pem   PRIVATE -> signs rim-<machine>.json
$OUT/rim-signer.cnf       extensions used, kept for the record

---- next -------------------------------------------------------
Nothing uses this key until mk-release.sh signs a RIM with it.
Before relying on it: a bundle signed with this key must be rejected by
rauc with the system.conf from recipes-core/rauc/files.
EOF
  exit 0
fi

if [ "$FLAVOUR" = "fit" ] || [ "$FLAVOUR" = "fit-prod" ]; then
  # ------------------------------------------------------- U-Boot FIT signer
  # Self-signed on purpose. U-Boot builds no chain when it verifies a FIT:
  # fdt_add_pubkey extracts the RSA modulus from this certificate into the
  # control FDT, and that modulus is the whole of what the board checks.
  # Issuing this leaf from the dev Signing CA would suggest a chain that
  # nothing verifies.
  #
  # RSA-2048 because the recipe invokes fdt_add_pubkey -a sha256,rsa2048;
  # a different length yields a key U-Boot will not match.
  #
  # Names are fixed by mkimage convention: <keyname>.key and <keyname>.crt,
  # with keyname = TACTIQ_FIT_KEY_NAME (default dev-fit).
  if [ "$FLAVOUR" = "fit-prod" ]; then
    KEYNAME="${TACTIQ_FIT_KEY_NAME:-release-fit}"
  else
    KEYNAME="${TACTIQ_FIT_KEY_NAME:-dev-fit}"
  fi
  if [ "$FLAVOUR" = "fit-prod" ]; then
    mkdir -p "$OUT"
  elif [ ! -d "$OUT" ]; then
    echo "ERROR: $OUT not found. Run '$0 dev' first." >&2
    exit 1
  fi
  for f in "$KEYNAME.key" "$KEYNAME.crt"; do
    if [ -e "$OUT/$f" ]; then
      echo "ERROR: $OUT/$f already exists. Refusing to reissue in place:" >&2
      echo "       a new key does not match the modulus already in u-boot.itb." >&2
      exit 1
    fi
  done
  cd "$OUT"

  echo "[1/1] FIT signer (self-signed)"
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 \
    $ENC -out "$KEYNAME.key"
  openssl req -x509 -new -sha256 \
    -key "$KEYNAME.key" \
    -days "$LEAF_DAYS" \
    -subj "/O=$ORG/CN=$LEAF_CN" \
    -out "$KEYNAME.crt"

  echo
  echo "---- verification ----------------------------------------------"
  openssl x509 -in "$KEYNAME.crt" -noout -subject -enddate
  echo "key bits:"
  openssl rsa -in "$KEYNAME.key" -noout -text | head -n 1

  cat <<EOF

---- files ------------------------------------------------------
$OUT/$KEYNAME.crt   PUBLIC  -> modulus goes into the U-Boot control FDT
$OUT/$KEYNAME.key   PRIVATE -> signs the kernel FIT

---- next -------------------------------------------------------
Nothing changes until TACTIQ_FIT_KEY_DIR points here (and, for a key
not named dev-fit, TACTIQ_FIT_KEY_NAME=$KEYNAME). Until then the
U-Boot recipe warns and leaves u-boot.itb without a verification key.
EOF
  exit 0
fi

if [ "$FLAVOUR" = "modsign-prod" ]; then
  # --------------------------------------------- kernel module signing key
  # Mirrors pki/dev/module-signing/module-signing-dev.pem, which matches the
  # kernel's own default genkey: RSA-4096, self-signed, CA:FALSE,
  # digitalSignature, subjectKeyIdentifier, 100 years. The kernel reads the
  # private key and the certificate from one PEM (TACTIQ_MODULE_SIG_KEY),
  # compiles the certificate into its builtin keyring and signs every module
  # with the key. No chain: the kernel trusts the certificate itself.
  mkdir -p "$OUT"
  if [ -e "$OUT/module-signing.pem" ]; then
    echo "ERROR: $OUT/module-signing.pem already exists. Refusing to reissue in place:" >&2
    echo "       a new key does not match the certificate in a built kernel." >&2
    exit 1
  fi
  cd "$OUT"

  cat > module-signing.cnf <<'EOF'
[req]
distinguished_name = dn
x509_extensions    = v3_modsign
prompt             = no
[dn]
[v3_modsign]
basicConstraints     = critical, CA:FALSE
keyUsage             = digitalSignature
subjectKeyIdentifier = hash
EOF

  echo "[1/1] Kernel module signing key (self-signed)"
  openssl req -x509 -new -newkey rsa:4096 -nodes -sha256 \
    -config module-signing.cnf \
    -days "$LEAF_DAYS" \
    -subj "/O=$ORG/CN=$LEAF_CN" \
    -keyout module-signing.key.tmp \
    -out module-signing.crt.tmp
  cat module-signing.key.tmp module-signing.crt.tmp > module-signing.pem
  rm -f module-signing.key.tmp module-signing.crt.tmp module-signing.cnf

  echo
  echo "---- verification ----------------------------------------------"
  openssl x509 -in module-signing.pem -noout -subject -enddate \
    -ext basicConstraints,keyUsage,subjectKeyIdentifier
  openssl pkey -in module-signing.pem -noout -text | head -n 1

  cat <<EOF

---- files ------------------------------------------------------
$OUT/module-signing.pem   PRIVATE key + certificate -> TACTIQ_MODULE_SIG_KEY

---- next -------------------------------------------------------
Set TACTIQ_MODULE_SIG_KEY to this file in the release build's local.conf.
EOF
  exit 0
fi

if [ "$FLAVOUR" = "ima" ] || [ "$FLAVOUR" = "ima-prod" ]; then
  for f in signing-ca.key.pem signing-ca.pem root-ca.pem; do
    if [ ! -e "$OUT/$f" ]; then
      echo "ERROR: $OUT/$f not found. Create the hierarchy first ($0 dev, or $0 prod DIR)." >&2
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
elif [ "$FLAVOUR" = "signer" ]; then
  for f in signing-ca.key.pem signing-ca.pem root-ca.pem; do
    if [ ! -e "$OUT/$f" ]; then
      echo "ERROR: $OUT/$f not found. Create the hierarchy first ($0 dev)." >&2
      exit 1
    fi
  done
  cd "$OUT"
elif [ -e "$OUT" ]; then
  echo "ERROR: $OUT already exists. Refusing to overwrite an existing hierarchy." >&2
  exit 1
fi

if [ "$FLAVOUR" = "ima" ] || [ "$FLAVOUR" = "ima-prod" ]; then
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
For dev the variables above are set in conf/distro/tactiq.conf; for a
release build set IMA_EVM_KEY_DIR to this directory in local.conf.
Every previously built image carries signatures from the old key.
EOF
  exit 0
fi

if [ "$FLAVOUR" = "signer" ]; then
  # ---------------------------------------------------- RAUC signer leaf
  # Reissues only the bundle signer, from the existing dev Signing CA.
  # The device keyring holds the Root CA alone, so boards accept bundles
  # signed by the new leaf with no change on the board. The old key and
  # certificate are replaced in place (git history keeps them); the new
  # ones are written under temporary names and moved into place only
  # after the chain verifies.
  cat > signer.cnf <<'EOF'
[v3_signer]
basicConstraints       = critical, CA:FALSE
keyUsage               = critical, digitalSignature
extendedKeyUsage       = critical, codeSigning
subjectKeyIdentifier   = hash
authorityKeyIdentifier = keyid:always
EOF

  echo "[1/1] RAUC bundle signer (leaf)"
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 \
    $ENC -out signer.key.pem.new
  openssl req -new -sha256 \
    -key signer.key.pem.new \
    -subj "/O=$ORG/CN=$LEAF_CN" \
    -out signer.csr
  openssl x509 -req -sha256 \
    -in signer.csr \
    -CA signing-ca.pem -CAkey signing-ca.key.pem -CAcreateserial \
    -days "$LEAF_DAYS" \
    -extfile signer.cnf -extensions v3_signer \
    -out signer.pem.new
  rm -f signer.csr

  echo
  echo "---- verification ----------------------------------------------"
  openssl verify -CAfile root-ca.pem -untrusted signing-ca.pem signer.pem.new
  mv signer.key.pem.new signer.key.pem
  mv signer.pem.new signer.pem
  echo
  echo "leaf key usage:"
  openssl x509 -in signer.pem -noout -text \
    | grep -A1 -E 'X509v3 (Key Usage|Extended Key Usage)'
  echo
  openssl x509 -in signer.pem -noout -subject -issuer -enddate

  cat <<EOF

---- files ------------------------------------------------------
$OUT/signer.pem       PUBLIC  -> bundle signer certificate
$OUT/signer.key.pem   PRIVATE -> bundle signer key

---- next -------------------------------------------------------
Root CA and Signing CA are unchanged: nothing to do on the board.
Bundles built before this carry the old leaf.
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
