#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEV_TLS_DIR="${REPO_ROOT}/configs/tls/dev"
OUT_DIR="${DEV_TLS_DIR}/generated"

mkdir -p "${OUT_DIR}"

ROOT_KEY="${OUT_DIR}/root-ca.key.pem"
ROOT_CERT="${OUT_DIR}/root-ca.pem"

generate_root() {
  if [[ -f "${ROOT_KEY}" && -f "${ROOT_CERT}" ]]; then
    echo "✅ Reusing existing dev root CA at ${ROOT_CERT}"
    return
  fi

  echo "🔐 Generating dev root CA..."
  openssl genrsa -out "${ROOT_KEY}" 2048 >/dev/null
  openssl req -x509 -new -nodes -key "${ROOT_KEY}" -sha256 -days 730 \
    -subj "/CN=TradePulse Dev Root/O=TradePulse Dev" \
    -out "${ROOT_CERT}" >/dev/null
}

generate_cert() {
  local name=$1
  local cn=$2
  local sans=$3

  local key="${OUT_DIR}/${name}.key.pem"
  local csr="${OUT_DIR}/${name}.csr"
  local cert="${OUT_DIR}/${name}.pem"

  echo "🔑 Generating key for ${name}..."
  openssl genrsa -out "${key}" 2048 >/dev/null

  echo "📄 Creating CSR for ${name}..."
  openssl req -new -key "${key}" -subj "/CN=${cn}/O=TradePulse Dev" -out "${csr}" >/dev/null

  echo "🪪 Signing certificate for ${name}..."
  openssl x509 -req -in "${csr}" -CA "${ROOT_CERT}" -CAkey "${ROOT_KEY}" -CAcreateserial \
    -out "${cert}" -days 365 -sha256 \
    -extfile <(printf "subjectAltName=%s\nextendedKeyUsage=serverAuth,clientAuth\n" "${sans}") >/dev/null

  rm -f "${csr}"
  chmod 600 "${key}"
  chmod 644 "${cert}"
}

echo "📂 Output directory: ${OUT_DIR}"
generate_root

generate_cert "tradepulse-server" "tradepulse.local" "DNS:tradepulse.local,DNS:localhost"
generate_cert "cortex-server" "cortex.local" "DNS:cortex.local,DNS:localhost"
generate_cert "cortex-db-server" "cortex-db" "DNS:cortex-db,DNS:localhost"
generate_cert "cortex-db-client" "cortex-db-client" "DNS:cortex-db-client,DNS:localhost"

echo ""
echo "✅ Development TLS material generated under ${OUT_DIR}"
echo "   - Point services at *.key.pem and *.pem from that directory"
echo "   - Files are gitignored; regenerate anytime if compromised"
